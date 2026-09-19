import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask, g

from teacher_app.materials import job_routes
from teacher_app.materials.job_runtime import MaterialJobRuntime
from teacher_app.worker import repository as worker_repository
from teacher_app.worker.schema import init_schema


class MaterialJobRoutesBaseFreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "jobs.sqlite"
        self.progress_dir = Path(self.temp.name) / "progress"
        self.progress_dir.mkdir()
        conn, kind = self.connect()
        try:
            init_schema(conn, kind)
        finally:
            conn.close()

        self.app = Flask(__name__ + str(id(self)))
        self.app.config.update(TESTING=True, SECRET_KEY="job-routes-test")
        self.actor = {
            "username": "admin",
            "role": "system_admin",
            "roles": ["system_admin"],
            "preferredGroup": "grpBio",
        }
        self.events = []
        self.deleted = []
        self.progress = []

        @self.app.before_request
        def bind_actor():
            g.teacher_user = self.actor

        self.common_db = patch(
            "teacher_app.common.db.get_connection",
            side_effect=self.connect,
        )
        self.common_db.start()
        self.addCleanup(self.common_db.stop)

        self.runtime = MaterialJobRuntime(
            upload_staging=self.upload_staging,
            staging_exists=lambda job: bool(job.get("stagingKey") or job.get("stagingPath")),
            delete_staging=self.delete_staging,
            cleanup_budget_state=lambda: self.events.append("budget-cleanup"),
            operations_status=lambda: {
                "workers": [{"workerId": "w1"}],
                "pendingJobs": 1,
                "processingJobs": 2,
                "retryJobs": 3,
                "failedJobs": 4,
                "r2Budget": {"ok": True},
            },
            staging_capability=lambda: {
                "available": True,
                "backend": "mega",
                "shared": True,
                "namespace": "_staging/material-jobs",
            },
            progress_path=lambda progress_id: self.progress_dir / f"{progress_id}.json",
            clear_progress=lambda progress_id: self.progress.append(("clear", progress_id)),
            set_progress=lambda progress_id, percent, stage, detail: self.progress.append(
                (progress_id, percent, stage, detail)
            ),
            sync_media_processing_metadata=lambda job, status: self.events.append(("media", job["id"], status)),
            connection_factory=self.connect,
            background_enabled=True,
            worker_enabled=True,
            max_attempts=5,
        )
        job_routes.register_material_job_routes(self.app, runtime=self.runtime)
        self.client = self.app.test_client()

    def connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def upload_staging(self, source, job_id, original_name):
        self.events.append(("stage", job_id, original_name, Path(source).read_bytes()))
        return "mega", f"/root/_staging/material-jobs/{job_id}/source{Path(original_name).suffix.lower()}", ""

    def delete_staging(self, row):
        self.events.append(("delete-staging", dict(row)))
        self.deleted.append(dict(row))

    def seed_job(self, job_id="job-1", *, status="failed", group="grpBio"):
        now = "2026-09-18T00:00:00+00:00"
        worker_repository.create_material_job(
            {
                "id": job_id,
                "status": status,
                "priority": 100,
                "created_at": now,
                "updated_at": now,
                "available_at": now,
                "payload": {"group": group, "originalName": "lesson.pdf"},
                "staging_path": "",
                "staging_backend": "mega",
                "staging_key": f"/staging/{job_id}/source.pdf",
                "original_name": "lesson.pdf",
                "material_id": f"material-{job_id}",
                "source_sha256": "a" * 64,
                "source_bytes": 12,
            },
            connection_factory=self.connect,
        )

    def test_direct_flask_registration_preserves_exact_routes_and_endpoints(self):
        expected = {
            ("/api/slides/upload-progress/<progress_id>", "api_upload_progress", "GET"),
            ("/api/material-jobs", "api_list_material_jobs", "GET"),
            ("/api/material-jobs/<job_id>", "api_get_material_job", "GET"),
            ("/api/material-jobs/upload", "api_enqueue_material_job", "POST"),
            ("/api/material-jobs/<job_id>/retry", "api_retry_material_job", "POST"),
            ("/api/material-jobs/<job_id>/cancel", "api_cancel_material_job", "POST"),
        }
        actual = set()
        for rule in self.app.url_map.iter_rules():
            for method in set(rule.methods) - {"HEAD", "OPTIONS"}:
                actual.add((rule.rule, rule.endpoint, method))
        self.assertTrue(expected.issubset(actual), sorted(expected - actual))
        self.assertIs(self.app.extensions["teacher_material_job_runtime"], self.runtime)

    def test_enqueue_uses_canonical_repository_after_staging_and_preserves_payload(self):
        response = self.client.post(
            "/api/material-jobs/upload",
            data={
                "file": (io.BytesIO(b"%PDF-1.4\nlesson"), "lesson.pdf"),
                "title": "Lesson",
                "group": "grpBio",
                "area": "pgy",
                "courseId": "course-1",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 202, response.get_data(as_text=True))
        body = response.get_json()
        job = worker_repository.get_material_job(
            body["jobId"], include_payload=True, connection_factory=self.connect
        )
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["maxAttempts"], 5)
        self.assertEqual(job["payload"]["group"], "grpBio")
        self.assertEqual(job["payload"]["area"], "pgy")
        self.assertEqual(job["payload"]["courseId"], "course-1")
        self.assertEqual(job["stagingBackend"], "mega")
        self.assertTrue(self.events[0][0] == "stage")
        self.assertEqual(self.events[1], ("media", body["jobId"], "queued"))
        self.assertEqual(self.progress[0], ("clear", body["jobId"]))
        self.assertEqual(self.progress[1][1:3], (9, "已加入背景佇列"))

    def test_web_byte_upload_normalizes_filename_and_rejects_macro_office(self):
        normalized = self.client.post(
            "/api/material-jobs/upload",
            data={
                "file": (io.BytesIO(b"safe text"), "..\\folder/e\u0301vidence\x00.txt"),
                "group": "grpBio",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(normalized.status_code, 202, normalized.get_data(as_text=True))
        job = worker_repository.get_material_job(
            normalized.get_json()["jobId"], include_payload=True, connection_factory=self.connect
        )
        self.assertEqual(job["originalName"], "évidence.txt")
        self.assertEqual(job["payload"]["originalName"], "évidence.txt")

        rejected = self.client.post(
            "/api/material-jobs/upload",
            data={"file": (io.BytesIO(b"macro"), "lesson.docm"), "group": "grpBio"},
            content_type="multipart/form-data",
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("巨集", rejected.get_json()["error"])

    def test_create_failure_cleans_staging_once_before_error_response(self):
        with patch.object(
            worker_repository,
            "create_material_job",
            side_effect=RuntimeError("db failed"),
        ):
            response = self.client.post(
                "/api/material-jobs/upload",
                data={"file": (io.BytesIO(b"%PDF-1.4\nlesson"), "lesson.pdf")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("db failed", response.get_json()["error"])
        self.assertEqual(len(self.deleted), 1)
        self.assertEqual([event for event in self.events if isinstance(event, tuple) and event[0] == "media"], [])

    def test_retry_preserves_status_checks_staging_and_progress_order(self):
        self.seed_job(status="failed")
        response = self.client.post("/api/material-jobs/job-1/retry")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["job"]["status"], "queued")
        self.assertEqual(self.progress[0], ("clear", "job-1"))
        self.assertEqual(self.progress[1][1:3], (9, "重新排隊"))
        job = worker_repository.get_material_job(
            "job-1", include_payload=True, connection_factory=self.connect
        )
        self.assertFalse(job["cancelRequested"])
        self.assertEqual(job["attempts"], 0)

    def test_retry_missing_staging_remains_410_without_mutation(self):
        self.seed_job(status="failed")
        runtime = self.app.extensions["teacher_material_job_runtime"]
        object.__setattr__(runtime, "staging_exists", lambda _job: False)
        response = self.client.post("/api/material-jobs/job-1/retry")
        self.assertEqual(response.status_code, 410)
        job = worker_repository.get_material_job("job-1", connection_factory=self.connect)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(self.progress, [])

    def test_cancel_preserves_processing_and_terminal_idempotence(self):
        self.seed_job("processing-job", status="processing")
        blocked = self.client.post("/api/material-jobs/processing-job/cancel")
        self.assertEqual(blocked.status_code, 409)

        self.seed_job("completed-job", status="completed")
        completed = self.client.post("/api/material-jobs/completed-job/cancel")
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.get_json()["job"]["status"], "completed")

        self.seed_job("queued-job", status="queued")
        cancelled = self.client.post("/api/material-jobs/queued-job/cancel")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.get_json()["job"]["status"], "cancelled")
        self.assertEqual(self.progress[-1][1:3], (0, "已取消"))

    def test_endpoint_aware_scope_allows_own_group_and_denies_cross_group(self):
        self.actor = {
            "username": "teacher",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredGroup": "grpBio",
        }
        own = self.client.post(
            "/api/material-jobs/upload",
            data={
                "file": (io.BytesIO(b"%PDF-1.4\nown"), "own.pdf"),
                "group": "grpBio",
            },
            content_type="multipart/form-data",
        )
        cross = self.client.post(
            "/api/material-jobs/upload",
            data={
                "file": (io.BytesIO(b"%PDF-1.4\ncross"), "cross.pdf"),
                "group": "grpHema",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(own.status_code, 202, own.get_data(as_text=True))
        self.assertEqual(cross.status_code, 403)
        self.assertEqual(cross.get_json()["error"], "此資源不在你的授權範圍。")

    def test_list_uses_runtime_ops_but_repository_jobs(self):
        self.seed_job()
        response = self.client.get("/api/material-jobs?limit=7")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["jobs"][0]["id"], "job-1")
        self.assertEqual(body["workers"], [{"workerId": "w1"}])
        self.assertEqual(body["r2Budget"], {"ok": True})
        self.assertEqual(body["pendingJobs"], 1)
        self.assertIn("budget-cleanup", self.events)


class MaterialJobCompatOwnerTests(unittest.TestCase):
    def test_owner_shape_is_adapted_only_at_registration_boundary(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        db_path = root / "jobs.sqlite"

        def connect():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.isolation_level = None
            return conn, "sqlite"

        conn, kind = connect()
        try:
            init_schema(conn, kind)
        finally:
            conn.close()

        app = Flask("material-job-compat")
        owner = SimpleNamespace(
            app=app,
            _db_conn=connect,
            upload_material_job_staging=lambda *_args: ("local", "", str(root / "source.pdf")),
            material_job_staging_exists=lambda _job: True,
            delete_material_job_staging=lambda _job: None,
            cleanup_r2_budget_state=lambda: None,
            material_job_operations_status=lambda: {},
            shared_staging_capability=lambda: {"available": True, "backend": "local", "shared": False},
            _upload_progress_path=lambda progress_id: root / f"{progress_id}.json",
            clear_upload_progress=lambda _progress_id: None,
            set_upload_progress=lambda *_args: None,
            sync_media_processing_metadata=lambda *_args: None,
            MATERIAL_BACKGROUND_JOBS=True,
            MATERIAL_WORKER_ENABLED=False,
            MATERIAL_JOB_MAX_ATTEMPTS=4,
        )
        registered = job_routes.register_material_job_routes(owner)
        self.assertIs(registered, app)
        runtime = app.extensions["teacher_material_job_runtime"]
        conn, kind = runtime.connection_factory()
        conn.close()
        self.assertEqual(kind, "sqlite")
        self.assertTrue(runtime.background_enabled())
        self.assertFalse(runtime.worker_enabled())
        self.assertEqual(runtime.max_attempts(), 4)


if __name__ == "__main__":
    unittest.main()
