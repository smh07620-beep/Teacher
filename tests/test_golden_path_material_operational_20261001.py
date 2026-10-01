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
from teacher_app.materials import repository as material_repository
from teacher_app.materials import schema as material_schema
from teacher_app.materials import service as material_service
from teacher_app.storage import providers
from teacher_app.worker import protocol as worker_protocol
from teacher_app.worker import repository as worker_repository
from teacher_app.worker.protocol_version import MATERIAL_WORKER_PROTOCOL_VERSION


class MaterialGoldenPathOperationalTests(unittest.TestCase):
    """Protect the human outcome, not just isolated material/Worker endpoints.

    GP-01 + GP-05:
      teacher direct upload -> queued job -> compatible Worker -> recoverable
      processing failure -> same R2 source is retried -> durable publish receipt
      -> completed job -> canonical material appears in the teaching catalog.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "material-golden-path.sqlite"
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
            schema_migrations._provider_publish_receipts_79(conn, kind)
            material_schema.init_schema(conn, kind)
        finally:
            conn.close()

    def connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def test_gp01_gp05_upload_worker_retry_then_material_is_really_usable(self):
        raw = b"%PDF-1.4\nGolden Path material\n%%EOF"
        source_sha = hashlib.sha256(raw).hexdigest()
        deleted_keys = []

        class FakeR2:
            def generate_presigned_url(self, operation, Params, ExpiresIn):
                return f"https://r2.example/{operation}/{Params['Key']}?ttl={ExpiresIn}"

            def head_object(self, **_kwargs):
                return {
                    "ContentLength": len(raw),
                    "ETag": '"golden-etag"',
                    "Metadata": {"sha256": source_sha},
                }

            def delete_object(self, **kwargs):
                deleted_keys.append(str(kwargs.get("Key") or ""))
                return {}

        fake_r2 = FakeR2()
        client = pgy_app.app.test_client()
        teacher = {
            "username": "teacher-golden-path",
            "role": "system_admin",
            "roles": ["system_admin", "clinical_teacher"],
            "preferredGroup": "grpBio",
        }
        web_headers = {"Origin": "http://localhost"}
        worker_headers = {"Authorization": "Bearer worker-secret"}
        worker_capabilities = {
            "protocolVersion": MATERIAL_WORKER_PROTOCOL_VERSION,
            "platform": "windows",
            "ffmpeg": {"available": True},
            "libreOffice": {"available": True},
        }

        with patch.object(auth_service, "current_user", return_value=teacher), patch.dict(
            os.environ,
            {
                "MATERIAL_WORKER_TOKEN": "worker-secret",
                "MATERIAL_DIRECT_UPLOAD_ENABLED": "true",
                "MATERIAL_DIRECT_UPLOAD_MAX_MB": "2048",
            },
        ), patch.object(providers, "r2_is_configured", return_value=True), patch.object(
            providers, "r2_client", return_value=fake_r2
        ), patch.object(providers, "R2_BUCKET_NAME", "teacher-test-bucket"), patch.object(
            self.runtime, "enforce_large_upload_budget", return_value=None
        ), patch.object(self.runtime, "release_reservation", return_value=None), patch.object(
            self.runtime, "record_r2_object", return_value=None
        ), patch.object(self.runtime, "record_r2_deleted", return_value=None), patch.object(
            self.runtime, "sync_media_processing_metadata", return_value=None
        ), patch.object(self.runtime, "delete_staging", side_effect=lambda job: deleted_keys.append(job.get("stagingKey", ""))):
            # Teacher starts a real direct-upload session linked to the course.
            init = client.post(
                "/api/material-upload/init",
                json={
                    "filename": "golden-path.pdf",
                    "size": len(raw),
                    "sha256": source_sha,
                    "title": "Golden Path 教材",
                    "desc": "完整流程驗收教材",
                    "group": "grpBio",
                    "area": "internal",
                    "courseId": "course-golden-path",
                    "materialType": "standard",
                },
                headers=web_headers,
            )
            self.assertEqual(init.status_code, 201, init.get_data(as_text=True))
            upload = init.get_json()
            self.assertEqual(upload["mode"], "single")

            accepted = client.post(
                f"/api/material-upload/{upload['uploadId']}/complete",
                json={"parts": [{"partNumber": 1, "etag": "golden-etag", "sha256": source_sha}]},
                headers=web_headers,
            )
            self.assertEqual(accepted.status_code, 202, accepted.get_data(as_text=True))
            self.assertEqual(accepted.get_json()["status"], "queued")

            queued = worker_repository.get_material_job(
                upload["jobId"], include_payload=True, connection_factory=self.connect
            )
            self.assertEqual(queued["status"], "queued")
            self.assertEqual(queued["stagingBackend"], "r2")
            staging_key = queued["stagingKey"]
            self.assertTrue(staging_key)

            # A current-protocol Worker owns the job. The first conversion fails.
            first_claim = client.post(
                "/api/material-worker/claim",
                json={"workerId": "golden-worker", "capabilities": worker_capabilities},
                headers=worker_headers,
            )
            self.assertEqual(first_claim.status_code, 200, first_claim.get_data(as_text=True))
            self.assertEqual(first_claim.get_json()["job"]["id"], upload["jobId"])

            retry = client.post(
                f"/api/material-worker/{upload['jobId']}/retry",
                json={
                    "workerId": "golden-worker",
                    "error": "LibreOffice conversion failed in Golden Path probe",
                },
                headers=worker_headers,
            )
            self.assertEqual(retry.status_code, 200, retry.get_data(as_text=True))
            self.assertEqual(retry.get_json()["status"], "retry_wait")

            waiting = worker_repository.get_material_job(
                upload["jobId"], include_payload=True, connection_factory=self.connect
            )
            self.assertEqual(waiting["status"], "retry_wait")
            self.assertEqual(waiting["stagingKey"], staging_key)
            self.assertIn("LibreOffice conversion failed", waiting["error"])
            self.assertEqual(deleted_keys, [], "recoverable Worker failure must preserve R2 source")
            self.assertIsNone(material_repository.get_material(upload["materialId"]))

            # Make the backoff window eligible and retry the *same* job/source.
            eligible = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)).isoformat()
            worker_repository.update_material_job(
                upload["jobId"],
                fields={"available_at": eligible},
                connection_factory=self.connect,
            )
            second_claim = client.post(
                "/api/material-worker/claim",
                json={"workerId": "golden-worker", "capabilities": worker_capabilities},
                headers=worker_headers,
            )
            self.assertEqual(second_claim.status_code, 200, second_claim.get_data(as_text=True))
            second_job = second_claim.get_json()["job"]
            self.assertEqual(second_job["id"], upload["jobId"])
            self.assertEqual(second_job["sourceSha256"], source_sha)
            self.assertEqual(second_job["attempts"], 2)

            # Provider publication is durable before Web marks the job completed.
            publish_key = worker_protocol.material_publish_key(
                upload["jobId"], upload["materialId"], source_sha, "mega"
            )
            result = {
                "storageBackend": "mega",
                "storageKey": f"/materials/{upload['materialId']}/source.pdf",
                "storageFilename": "source.pdf",
                "pageCount": 1,
                "storageMeta": {"previewMode": "single_pdf"},
                "publishKey": publish_key,
                "publishSourceSha256": source_sha,
            }
            published = client.post(
                f"/api/material-worker/{upload['jobId']}/published",
                json={
                    "workerId": "golden-worker",
                    "publishKey": publish_key,
                    "backend": "mega",
                    "sourceSha256": source_sha,
                    "result": result,
                },
                headers=worker_headers,
            )
            self.assertEqual(published.status_code, 200, published.get_data(as_text=True))

            completed = client.post(
                f"/api/material-worker/{upload['jobId']}/complete",
                json={"workerId": "golden-worker", "publishKey": publish_key, "result": result},
                headers=worker_headers,
            )
            self.assertEqual(completed.status_code, 200, completed.get_data(as_text=True))
            self.assertEqual(completed.get_json()["status"], "completed")

        final_job = worker_repository.get_material_job(
            upload["jobId"], include_payload=True, connection_factory=self.connect
        )
        self.assertEqual(final_job["status"], "completed")
        self.assertEqual(final_job["error"], "")
        self.assertEqual(final_job["stagingKey"], "")
        self.assertEqual(deleted_keys, [staging_key])

        # This is the user-visible outcome: the canonical material exists with
        # the same course/scope chosen by the teacher and is present in catalog.
        material = material_repository.get_material(upload["materialId"])
        self.assertIsNotNone(material)
        self.assertEqual(material["title"], "Golden Path 教材")
        self.assertEqual(material["courseId"], "course-golden-path")
        self.assertEqual(material["group"], "grpBio")
        self.assertEqual(material["area"], "internal")
        self.assertEqual(material["viewerMode"], "preview_pdf")
        self.assertEqual(material["storageBackend"], "mega")

        visible = [
            item for item in material_service.list_materials("internal")
            if item.get("id") == upload["materialId"]
        ]
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["courseId"], "course-golden-path")
        self.assertEqual(visible[0]["previewUrl"], f"/material-preview/{upload['materialId']}")


if __name__ == "__main__":
    unittest.main()
