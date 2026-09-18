import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask, g

from teacher_app.worker import repository as worker_repository
from teacher_app.worker.routes import register_free_worker
from teacher_app.worker.schema import init_schema
from teacher_app.worker.web_runtime import WorkerWebRuntime


class _FakeR2:
    def __init__(self, events):
        self.events = events
        self.expected_bytes = 0
        self.sha256 = ""

    def create_multipart_upload(self, **kwargs):
        self.events.append(("r2.create", kwargs["Key"]))
        metadata = kwargs.get("Metadata") or {}
        self.expected_bytes = int(metadata.get("expectedbytes") or 0)
        self.sha256 = str(metadata.get("sha256") or "")
        return {"UploadId": "remote-upload"}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.events.append(("r2.presign", operation, Params.get("PartNumber"), ExpiresIn))
        return f"https://r2.example/{operation}/{Params.get('PartNumber', 'source')}"

    def complete_multipart_upload(self, **kwargs):
        self.events.append(("r2.complete", kwargs["Key"]))
        return {}

    def head_object(self, **kwargs):
        self.events.append(("r2.head", kwargs["Key"]))
        return {
            "ContentLength": self.expected_bytes,
            "Metadata": {"sha256": self.sha256},
        }

    def abort_multipart_upload(self, **kwargs):
        self.events.append(("r2.abort", kwargs["Key"]))
        return {}

    def delete_object(self, **kwargs):
        self.events.append(("r2.delete", kwargs["Key"]))
        return {}


class WorkerRoutesRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "worker.sqlite"
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

        self.app = Flask("worker-runtime-test-" + str(id(self)))
        self.app.config.update(TESTING=True, SECRET_KEY="worker-runtime-test")
        self.actor = {
            "username": "admin",
            "role": "system_admin",
            "roles": ["system_admin"],
            "preferredGroup": "grpBio",
        }
        self.events = []
        self.r2 = _FakeR2(self.events)

        @self.app.before_request
        def bind_actor():
            g.teacher_user = self.actor

        self.runtime = WorkerWebRuntime(
            cleanup_budget_state=lambda: self.events.append("budget.cleanup"),
            enforce_large_upload_budget=lambda upload_id, key, size: self.events.append(
                ("budget.enforce", upload_id, key, size)
            ),
            release_reservation=lambda upload_id, reason: self.events.append(
                ("budget.release", upload_id, reason)
            ),
            budget_status=lambda: {},
            download_staging=self.download_staging,
            delete_staging=lambda job: self.events.append(("staging.delete", job["id"])),
            commit_result=self.commit_result,
            sync_media_processing_metadata=lambda job, status, *detail: self.events.append(
                ("media.sync", job["id"], status, *detail)
            ),
            connection_factory=self.connect,
            worker_token="worker-secret",
            direct_upload_enabled=True,
            direct_upload_max_mb=64,
            worker_url_ttl_seconds=900,
            max_attempts=4,
            r2_client_factory=lambda: self.r2,
            r2_is_configured=lambda: True,
            r2_bucket_name="bucket",
            record_r2_object=lambda key, size, **kwargs: self.events.append(
                ("ledger.record", key, size, kwargs)
            ),
            record_r2_deleted=lambda key: self.events.append(("ledger.deleted", key)),
        )
        register_free_worker(self.app, runtime=self.runtime)
        self.client = self.app.test_client()

    def connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def download_staging(self, _job, target):
        Path(target).write_bytes(b"worker-source")
        return Path(target)

    def commit_result(self, job, _result):
        self.events.append(("commit", job["id"]))
        return {"id": job["materialId"]}

    def seed_job(self, job_id="job-1", *, status="queued"):
        now = "2026-09-18T00:00:00+00:00"
        return worker_repository.create_material_job(
            {
                "id": job_id,
                "status": status,
                "priority": 100,
                "created_at": now,
                "updated_at": now,
                "available_at": now,
                "max_attempts": 4,
                "payload": {"originalName": "lesson.txt", "group": "grpBio"},
                "staging_path": str(Path(self.temp.name) / "lesson.txt"),
                "staging_backend": "local",
                "staging_key": "",
                "original_name": "lesson.txt",
                "material_id": "material-1",
                "source_sha256": "a" * 64,
                "source_bytes": 12,
            },
            connection_factory=self.connect,
        )

    @staticmethod
    def worker_headers(worker_id=None):
        headers = {"Authorization": "Bearer worker-secret"}
        if worker_id:
            headers["X-Teacher-Worker-Id"] = worker_id
        return headers

    def test_direct_flask_registration_preserves_worker_routes_and_endpoints(self):
        expected = {
            ("/api/material-worker/claim", "material_worker_claim", "POST"),
            ("/api/material-worker/<job_id>/source", "material_worker_source", "GET"),
            ("/api/material-worker/heartbeat", "material_worker_heartbeat", "POST"),
            ("/api/material-worker/<job_id>/heartbeat", "material_worker_heartbeat", "POST"),
            ("/api/material-worker/<job_id>/complete", "material_worker_complete", "POST"),
            ("/api/material-worker/<job_id>/retry", "material_worker_retry", "POST"),
            ("/api/material-worker/<job_id>/fail", "material_worker_fail", "POST"),
            ("/api/material-upload/init", "material_upload_init", "POST"),
            ("/api/material-upload/<upload_id>/complete", "material_upload_complete", "POST"),
            ("/api/material-upload/<upload_id>/abort", "material_upload_abort", "POST"),
        }
        actual = set()
        for rule in self.app.url_map.iter_rules():
            for method in set(rule.methods) - {"HEAD", "OPTIONS"}:
                actual.add((rule.rule, rule.endpoint, method))
        self.assertTrue(expected.issubset(actual), sorted(expected - actual))
        self.assertIs(self.app.extensions["teacher_worker_web_runtime"], self.runtime)

    def test_worker_token_claim_heartbeat_and_owned_completion_contract(self):
        self.seed_job()
        denied = self.client.post("/api/material-worker/claim", json={"workerId": "worker-a"})
        self.assertEqual(denied.status_code, 401)

        claimed = self.client.post(
            "/api/material-worker/claim",
            json={"workerId": "worker-a", "capabilities": {}},
            headers=self.worker_headers(),
        )
        self.assertEqual(claimed.status_code, 200, claimed.get_data(as_text=True))
        self.assertEqual(claimed.get_json()["job"]["id"], "job-1")

        wrong_owner = self.client.post(
            "/api/material-worker/job-1/heartbeat",
            json={"workerId": "worker-b"},
            headers=self.worker_headers(),
        )
        self.assertEqual(wrong_owner.status_code, 409)

        completed = self.client.post(
            "/api/material-worker/job-1/complete",
            json={"workerId": "worker-a", "result": {}},
            headers=self.worker_headers(),
        )
        self.assertEqual(completed.status_code, 200, completed.get_data(as_text=True))
        self.assertEqual(completed.get_json(), {"cleanupPending": False, "ok": True, "status": "completed"})
        job = worker_repository.get_material_job("job-1", connection_factory=self.connect)
        self.assertEqual(job["status"], "completed")
        self.assertLess(self.events.index(("commit", "job-1")), self.events.index(("staging.delete", "job-1")))
        self.assertLess(
            self.events.index(("staging.delete", "job-1")),
            self.events.index(("media.sync", "job-1", "completed")),
        )

    def test_direct_upload_init_uses_canonical_endpoint_scope(self):
        self.actor = {
            "username": "teacher",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredGroup": "grpBio",
        }
        body = {
            "filename": "movie.mp4",
            "size": 8 * 1024 * 1024,
            "sha256": "a" * 64,
            "partSizeMb": 8,
            "group": "grpBio",
        }
        own = self.client.post("/api/material-upload/init", json=body)
        self.assertEqual(own.status_code, 201, own.get_data(as_text=True))
        cross = self.client.post("/api/material-upload/init", json={**body, "group": "grpHema"})
        self.assertEqual(cross.status_code, 403)
        self.assertEqual(cross.get_json()["error"], "此資源不在你的授權範圍。")

    def test_multipart_complete_preserves_accounting_then_job_then_release_order(self):
        init = self.client.post(
            "/api/material-upload/init",
            json={
                "filename": "movie.mp4",
                "size": 8 * 1024 * 1024,
                "sha256": "b" * 64,
                "partSizeMb": 8,
                "group": "grpBio",
            },
        )
        self.assertEqual(init.status_code, 201, init.get_data(as_text=True))
        data = init.get_json()
        complete = self.client.post(
            f"/api/material-upload/{data['uploadId']}/complete",
            json={"parts": [{"partNumber": 1, "etag": "etag-1"}]},
        )
        self.assertEqual(complete.status_code, 202, complete.get_data(as_text=True))
        self.assertEqual(complete.get_json()["status"], "queued")
        job = worker_repository.get_material_job(data["jobId"], connection_factory=self.connect)
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["maxAttempts"], 4)

        record_index = next(i for i, event in enumerate(self.events) if isinstance(event, tuple) and event[0] == "ledger.record")
        media_index = self.events.index(("media.sync", data["jobId"], "queued"))
        release_index = self.events.index(("budget.release", data["uploadId"], "completed"))
        self.assertLess(record_index, media_index)
        self.assertLess(media_index, release_index)

    def test_multipart_validation_failure_preserves_abort_delete_ledger_release_order(self):
        init = self.client.post(
            "/api/material-upload/init",
            json={
                "filename": "movie.mp4",
                "size": 8 * 1024 * 1024,
                "sha256": "c" * 64,
                "partSizeMb": 8,
                "group": "grpBio",
            },
        )
        data = init.get_json()
        self.r2.expected_bytes = 1
        failed = self.client.post(
            f"/api/material-upload/{data['uploadId']}/complete",
            json={"parts": [{"partNumber": 1, "etag": "etag-1"}]},
        )
        self.assertEqual(failed.status_code, 400, failed.get_data(as_text=True))
        session = worker_repository.get_upload_session(data["uploadId"], connection_factory=self.connect)
        self.assertEqual(session["status"], "failed")

        abort_index = next(i for i, event in enumerate(self.events) if isinstance(event, tuple) and event[0] == "r2.abort")
        delete_index = next(i for i, event in enumerate(self.events) if isinstance(event, tuple) and event[0] == "r2.delete")
        ledger_index = next(i for i, event in enumerate(self.events) if isinstance(event, tuple) and event[0] == "ledger.deleted")
        release_index = self.events.index(("budget.release", data["uploadId"], "validation_failed"))
        self.assertLess(abort_index, delete_index)
        self.assertLess(delete_index, ledger_index)
        self.assertLess(ledger_index, release_index)

    def test_abort_keeps_remote_abort_before_status_release(self):
        init = self.client.post(
            "/api/material-upload/init",
            json={
                "filename": "movie.mp4",
                "size": 8 * 1024 * 1024,
                "sha256": "d" * 64,
                "partSizeMb": 8,
                "group": "grpBio",
            },
        )
        data = init.get_json()
        aborted = self.client.post(f"/api/material-upload/{data['uploadId']}/abort")
        self.assertEqual(aborted.status_code, 200)
        session = worker_repository.get_upload_session(data["uploadId"], connection_factory=self.connect)
        self.assertEqual(session["status"], "aborted")
        abort_index = next(i for i, event in enumerate(self.events) if isinstance(event, tuple) and event[0] == "r2.abort")
        release_index = self.events.index(("budget.release", data["uploadId"], "aborted"))
        self.assertLess(abort_index, release_index)


if __name__ == "__main__":
    unittest.main()
