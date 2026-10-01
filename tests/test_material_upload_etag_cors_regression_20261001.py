import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask, g

from teacher_app.worker import repository as worker_repository
from teacher_app.worker.routes import register_free_worker
from teacher_app.worker.schema import init_schema
from teacher_app.worker.web_runtime import WorkerWebRuntime


class _SinglePutR2:
    def __init__(self):
        self.expected_bytes = 0
        self.deleted = []

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://r2.example/{operation}/{Params['Key']}?ttl={ExpiresIn}"

    def head_object(self, **_kwargs):
        return {
            "ContentLength": self.expected_bytes,
            "ETag": '"server-authoritative-etag"',
            "Metadata": {},
        }

    def delete_object(self, **kwargs):
        self.deleted.append(str(kwargs.get("Key") or ""))
        return {}


class MaterialUploadEtagCorsRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "material-upload-etag.sqlite"
        conn, kind = self.connect()
        try:
            init_schema(conn, kind)
            conn.execute(
                """
                CREATE TABLE material_worker_heartbeats (
                    worker_id TEXT PRIMARY KEY,
                    last_seen TEXT NOT NULL,
                    capabilities TEXT NOT NULL DEFAULT '{}',
                    current_job_id TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE material_upload_sessions (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    material_id TEXT NOT NULL,
                    staging_key TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    source_bytes INTEGER NOT NULL,
                    r2_upload_id TEXT NOT NULL,
                    part_size INTEGER NOT NULL,
                    expected_parts INTEGER NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    completed_parts TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'uploading',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        finally:
            conn.close()

        self.app = Flask("material-upload-etag-cors-regression")
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.r2 = _SinglePutR2()
        self.events = []

        @self.app.before_request
        def bind_actor():
            g.teacher_user = {
                "username": "admin",
                "role": "system_admin",
                "roles": ["system_admin"],
                "preferredGroup": "grpBio",
            }

        def fail_metadata_sync(*_args, **_kwargs):
            self.events.append("media-sync-attempted")
            raise RuntimeError("optional reporting database is unavailable")

        runtime = WorkerWebRuntime(
            cleanup_budget_state=lambda: None,
            enforce_large_upload_budget=lambda upload_id, key, size: self.events.append(
                ("budget", upload_id, key, size)
            ),
            release_reservation=lambda upload_id, reason: self.events.append(
                ("release", upload_id, reason)
            ),
            budget_status=lambda: {},
            download_staging=lambda *_args, **_kwargs: None,
            delete_staging=lambda *_args, **_kwargs: None,
            commit_result=lambda *_args, **_kwargs: {},
            sync_media_processing_metadata=fail_metadata_sync,
            connection_factory=self.connect,
            worker_token="worker-secret",
            direct_upload_enabled=True,
            direct_upload_max_mb=64,
            worker_url_ttl_seconds=900,
            max_attempts=3,
            r2_client_factory=lambda: self.r2,
            r2_is_configured=lambda: True,
            r2_bucket_name="bucket",
            record_r2_object=lambda key, size, **kwargs: self.events.append(
                ("ledger", key, size, kwargs)
            ),
            record_r2_deleted=lambda key: self.events.append(("deleted", key)),
        )
        register_free_worker(self.app, runtime=runtime)
        self.client = self.app.test_client()

    def connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def test_single_put_completes_without_browser_visible_etag_and_replays_safely(self):
        source_bytes = 4 * 1024 * 1024
        init = self.client.post(
            "/api/material-upload/init",
            json={
                "filename": "lesson.pdf",
                "size": source_bytes,
                "hashStrategy": "sha256-parts-v1",
                "partSizeMb": 16,
                "group": "grpBio",
            },
        )
        self.assertEqual(init.status_code, 201, init.get_data(as_text=True))
        upload = init.get_json()
        self.assertEqual(upload["mode"], "single")
        self.r2.expected_bytes = source_bytes

        source_sha = "e" * 64
        complete_body = {
            "parts": [
                {
                    "partNumber": 1,
                    "sha256": source_sha,
                    # Deliberately omit ETag: a successful R2 PUT may hide it
                    # from browser JavaScript unless CORS ExposeHeaders is set.
                }
            ]
        }
        completed = self.client.post(
            f"/api/material-upload/{upload['uploadId']}/complete",
            json=complete_body,
        )
        self.assertEqual(completed.status_code, 202, completed.get_data(as_text=True))
        self.assertEqual(completed.get_json()["status"], "queued")
        self.assertEqual(self.r2.deleted, [])
        self.assertIn("media-sync-attempted", self.events)

        session = worker_repository.get_upload_session(
            upload["uploadId"], connection_factory=self.connect
        )
        self.assertEqual(session["status"], "completed")
        self.assertEqual(session["completed_parts"][0]["ETag"], '"server-authoritative-etag"')
        self.assertEqual(session["completed_parts"][0]["SHA256"], source_sha)

        job = worker_repository.get_material_job(
            upload["jobId"], include_payload=True, connection_factory=self.connect
        )
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["sourceSha256"], source_sha)
        self.assertEqual(job["payload"]["sourceSha256"], source_sha)

        replay = self.client.post(
            f"/api/material-upload/{upload['uploadId']}/complete",
            json=complete_body,
        )
        self.assertEqual(replay.status_code, 200, replay.get_data(as_text=True))
        self.assertTrue(replay.get_json()["replayed"])
        self.assertEqual(replay.get_json()["jobId"], upload["jobId"])
        self.assertEqual(self.r2.deleted, [])


if __name__ == "__main__":
    unittest.main()
