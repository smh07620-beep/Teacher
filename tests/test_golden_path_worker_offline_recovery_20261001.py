import datetime as dt
import hashlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as appmod
import pgy_app
import schema_migrations
from teacher_app.auth import service as auth_service
from teacher_app.common import db as common_db
from teacher_app.courses import repository as course_repository
from teacher_app.courses import schema as course_schema
from teacher_app.materials import schema as material_schema
from teacher_app.storage import providers
from teacher_app.worker import repository as worker_repository
from teacher_app.worker.protocol_version import MATERIAL_WORKER_PROTOCOL_VERSION


class WorkerOfflineRecoveryGoldenPathTests(unittest.TestCase):
    """GP-06: an upload queued while Worker is offline survives until the Worker returns."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "worker-offline-golden-path.sqlite"
        self.runtime = pgy_app.app.extensions["teacher_worker_web_runtime"]

        runtime_patch = patch.object(self.runtime, "connection_factory", self.connect)
        legacy_patch = patch.object(appmod, "_db_conn", self.connect)
        common_patch = patch.object(common_db, "get_connection", self.connect)
        runtime_patch.start(); legacy_patch.start(); common_patch.start()
        self.addCleanup(runtime_patch.stop)
        self.addCleanup(legacy_patch.stop)
        self.addCleanup(common_patch.stop)

        appmod.init_material_jobs_db()
        conn, kind = self.connect()
        try:
            schema_migrations._b_free_local_worker_67(conn, kind)
            course_schema.init_schema(conn, kind)
            material_schema.init_schema(conn, kind)
        finally:
            conn.close()

        course_repository.create_course(
            course_id="course-worker-offline",
            area="internal",
            group="grpBio",
            title="Worker Offline Recovery",
            description="GP-06",
            date_added=dt.datetime.now(dt.timezone.utc).isoformat(),
        )

    def connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def test_offline_queue_is_claimed_as_same_job_when_worker_returns(self):
        raw = b"%PDF-1.4\nworker offline recovery\n%%EOF"
        source_sha = hashlib.sha256(raw).hexdigest()

        class FakeR2:
            def generate_presigned_url(self, operation, Params, ExpiresIn):
                return f"https://r2.example/{operation}/{Params['Key']}?ttl={ExpiresIn}"

            def head_object(self, **_kwargs):
                return {
                    "ContentLength": len(raw),
                    "ETag": '"offline-etag"',
                    "Metadata": {"sha256": source_sha},
                }

        client = pgy_app.app.test_client()
        teacher = {
            "username": "teacher-worker-offline",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredGroup": "grpBio",
        }
        web_headers = {"Origin": "http://localhost"}
        worker_headers = {"Authorization": "Bearer worker-secret"}

        with patch.object(auth_service, "current_user", return_value=teacher), patch.dict(
            os.environ,
            {
                "MATERIAL_WORKER_TOKEN": "worker-secret",
                "MATERIAL_DIRECT_UPLOAD_ENABLED": "true",
                "MATERIAL_DIRECT_UPLOAD_MAX_MB": "2048",
            },
        ), patch.object(providers, "r2_is_configured", return_value=True), patch.object(
            providers, "r2_client", return_value=FakeR2()
        ), patch.object(providers, "R2_BUCKET_NAME", "teacher-test-bucket"), patch.object(
            self.runtime, "enforce_large_upload_budget", return_value=None
        ), patch.object(self.runtime, "release_reservation", return_value=None), patch.object(
            self.runtime, "record_r2_object", return_value=None
        ), patch.object(self.runtime, "sync_media_processing_metadata", return_value=None):
            init = client.post(
                "/api/material-upload/init",
                json={
                    "filename": "worker-offline.pdf",
                    "size": len(raw),
                    "sha256": source_sha,
                    "title": "Worker 離線教材",
                    "desc": "Worker 回來後應接續同一工作",
                    "group": "grpBio",
                    "area": "internal",
                    "courseId": "course-worker-offline",
                    "materialType": "standard",
                },
                headers=web_headers,
            )
            self.assertEqual(init.status_code, 201, init.get_data(as_text=True))
            upload = init.get_json()

            accepted = client.post(
                f"/api/material-upload/{upload['uploadId']}/complete",
                json={"parts": [{"partNumber": 1, "etag": "offline-etag", "sha256": source_sha}]},
                headers=web_headers,
            )
            self.assertEqual(accepted.status_code, 202, accepted.get_data(as_text=True))
            self.assertEqual(accepted.get_json()["status"], "queued")

            # No Worker has contacted the service yet. The source/job must stay safe.
            queued = worker_repository.get_material_job(
                upload["jobId"], include_payload=True, connection_factory=self.connect
            )
            self.assertEqual(queued["status"], "queued")
            self.assertEqual(queued["stagingBackend"], "r2")
            self.assertTrue(queued["stagingKey"])
            self.assertEqual(queued["sourceSha256"], source_sha)
            self.assertEqual(int(queued.get("attempts") or 0), 0)
            staging_key = queued["stagingKey"]

            # Worker comes back later and must claim the exact queued job/source.
            # The claim response intentionally does not expose stagingKey; verify
            # persistence through the repository instead of weakening the API.
            claim = client.post(
                "/api/material-worker/claim",
                json={
                    "workerId": "worker-back-online",
                    "capabilities": {
                        "protocolVersion": MATERIAL_WORKER_PROTOCOL_VERSION,
                        "platform": "windows",
                        "ffmpeg": {"available": True},
                        "libreOffice": {"available": True},
                    },
                },
                headers=worker_headers,
            )
            self.assertEqual(claim.status_code, 200, claim.get_data(as_text=True))
            claimed = claim.get_json()["job"]
            self.assertEqual(claimed["id"], upload["jobId"])
            self.assertEqual(claimed["sourceSha256"], source_sha)
            self.assertEqual(claimed["attempts"], 1)

            persisted = worker_repository.get_material_job(
                upload["jobId"], include_payload=True, connection_factory=self.connect
            )
            self.assertEqual(persisted["status"], "processing")
            self.assertEqual(persisted["stagingKey"], staging_key)
            self.assertEqual(persisted["sourceSha256"], source_sha)


if __name__ == "__main__":
    unittest.main()
