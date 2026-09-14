import datetime as dt
import hashlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as appmod
import material_worker
import schema_migrations


ROOT = Path(__file__).parents[1]


class RenderWorkerSchemeBTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "jobs.sqlite"

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def with_queue(self):
        patcher = patch.object(appmod, "_db_conn", self.connect)
        patcher.start()
        self.addCleanup(patcher.stop)
        appmod.init_material_jobs_db()

    def test_web_entrypoint_never_starts_worker(self):
        source = ROOT.joinpath("run_web.sh").read_text(encoding="utf-8")
        self.assertIn("pgy_app:app", source)
        self.assertNotIn("material_worker.py", source)
        self.assertNotIn("worker_pid", source)

    def test_render_blueprint_has_separate_free_worker(self):
        source = ROOT.joinpath("render.yaml").read_text(encoding="utf-8")
        self.assertIn("type: worker", source)
        self.assertIn("name: biochemical-training-material-worker", source)
        self.assertIn("dockerCommand: python -u material_worker.py", source)
        self.assertIn("MATERIAL_WORKER_ENABLED", source)

    def test_staging_metadata_has_no_web_local_path(self):
        self.with_queue()
        appmod.create_material_job(
            job_id="job-shared", payload={"originalName": "lesson.pdf"},
            staging_backend="mega", staging_key="/root/_staging/material-jobs/job-shared/source.pdf",
            staging_path="", source_sha256="a" * 64, source_bytes=5,
            material_id="material-shared", original_name="lesson.pdf",
        )
        job = appmod.get_material_job("job-shared", include_payload=True)
        self.assertEqual(job["stagingBackend"], "mega")
        self.assertEqual(job["stagingPath"], "")
        self.assertIn("_staging/material-jobs", job["stagingKey"])

    def test_web_upload_stages_before_creating_runnable_job(self):
        self.with_queue()
        with patch.object(appmod, "require_admin", return_value=None), patch.object(appmod, "upload_material_job_staging", return_value=("mega", "/root/_staging/material-jobs/j/source.pdf", "")):
            response = appmod.app.test_client().post(
                "/api/material-jobs/upload",
                data={"file": (io.BytesIO(b"%PDF-1.4\nminimal"), "lesson.pdf"), "title": "Shared staging"},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 202, response.get_data(as_text=True))
        job = appmod.get_material_job(response.get_json()["jobId"], include_payload=True)
        self.assertEqual(job["stagingBackend"], "mega")
        self.assertEqual(job["stagingPath"], "")

    def test_db_create_failure_cleans_orphan_staging(self):
        self.with_queue()
        staging = {"stagingBackend": "mega", "stagingKey": "/root/_staging/material-jobs/j/source.pdf", "stagingPath": ""}
        with patch.object(appmod, "require_admin", return_value=None), patch.object(appmod, "upload_material_job_staging", return_value=("mega", staging["stagingKey"], "")), patch.object(appmod, "create_material_job", side_effect=RuntimeError("db failed")), patch.object(appmod, "delete_material_job_staging") as cleanup:
            response = appmod.app.test_client().post(
                "/api/material-jobs/upload",
                data={"file": (io.BytesIO(b"%PDF-1.4\nminimal"), "lesson.pdf")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 400)
        cleanup.assert_called_once_with(staging)

    def test_worker_rejects_sha_and_size_mismatch(self):
        source = Path(self.temp.name) / "lesson.txt"
        source.write_text("safe learning material", encoding="utf-8")
        base_job = {"payload": {"originalName": "lesson.txt"}, "sourceBytes": source.stat().st_size, "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        self.assertEqual(material_worker._validate_downloaded_source(source, base_job), "lesson.txt")
        with self.assertRaisesRegex(RuntimeError, "大小不符"):
            material_worker._validate_downloaded_source(source, {**base_job, "sourceBytes": 1})
        with self.assertRaisesRegex(RuntimeError, "SHA256"):
            material_worker._validate_downloaded_source(source, {**base_job, "sourceSha256": "0" * 64})

    def test_success_deletes_staging_and_retry_retains_it(self):
        source = Path(self.temp.name) / "source.txt"
        source.write_text("trusted", encoding="utf-8")
        job = {"id": "job-success", "attempts": 1, "maxAttempts": 2, "materialId": "m1", "sourceBytes": source.stat().st_size, "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(), "payload": {"originalName": "source.txt", "materialId": "m1"}, "stagingBackend": "local", "stagingPath": str(source)}
        with patch.object(appmod, "get_material", return_value=None), patch.object(appmod, "download_material_job_staging", side_effect=lambda _job, target: target.write_bytes(source.read_bytes()) or target), patch.object(material_worker, "_post_sync_upload", return_value={"id": "m1"}), patch.object(appmod, "delete_material_job_staging") as deleted, patch.object(appmod, "_update_material_job"), patch.object(appmod, "set_upload_progress"), patch.object(appmod, "sync_media_processing_metadata"):
            material_worker.process_job(job)
        deleted.assert_called_once_with(job)
        with patch.object(appmod, "get_material", return_value=None), patch.object(appmod, "download_material_job_staging", side_effect=RuntimeError("storage unavailable")), patch.object(appmod, "delete_material_job_staging") as deleted, patch.object(appmod, "_update_material_job") as updated, patch.object(appmod, "set_upload_progress"), patch.object(appmod, "sync_media_processing_metadata"):
            material_worker.process_job(job)
        deleted.assert_not_called()
        self.assertEqual(updated.call_args.kwargs["status"], "retry_wait")

    def test_stale_recovery_and_terminal_retention(self):
        self.with_queue()
        local = Path(self.temp.name) / "staging" / "source.txt"
        local.parent.mkdir(); local.write_text("ok", encoding="utf-8")
        appmod.create_material_job(job_id="job-stale", payload={"originalName": "source.txt"}, staging_backend="local", staging_key="", staging_path=str(local), source_sha256="a" * 64, source_bytes=2, material_id="m2", original_name="source.txt")
        conn, _ = self.connect()
        try:
            old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)).isoformat()
            conn.execute("UPDATE material_jobs SET status='processing', updated_at=? WHERE id='job-stale'", (old,))
        finally:
            conn.close()
        with patch.object(appmod, "MATERIAL_JOB_STALE_SECONDS", 300):
            self.assertEqual(appmod.recover_stale_material_jobs(), 1)
        self.assertEqual(appmod.get_material_job("job-stale")["status"], "queued")
        # Failed staging survives until the retention cleanup window, not a retry.
        conn, _ = self.connect()
        try:
            conn.execute("UPDATE material_jobs SET status='failed', updated_at=? WHERE id='job-stale'", (dt.datetime.now(dt.timezone.utc).isoformat(),))
        finally:
            conn.close()
        appmod.cleanup_material_job_staging()
        self.assertTrue(local.exists())

    def test_0067_shared_staging_extension_repeats_safely_on_sqlite(self):
        self.with_queue()
        conn, kind = self.connect()
        try:
            schema_migrations._render_worker_shared_staging_67(conn, kind)
            schema_migrations._render_worker_shared_staging_67(conn, kind)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(material_jobs)")}
        finally:
            conn.close()
        self.assertTrue({"staging_backend", "staging_key", "original_name"}.issubset(cols))

    def test_media_module_is_helpers_not_a_competing_worker(self):
        source = ROOT.joinpath("media_processing_67.py").read_text(encoding="utf-8")
        self.assertIn("material_jobs", source)
        self.assertNotIn("def worker_once", source)
        self.assertNotIn("shell=True", source)


if __name__ == "__main__":
    unittest.main()
