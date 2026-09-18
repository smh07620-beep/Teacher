import datetime as dt
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as appmod
import material_worker
import pgy_app
import schema_migrations
from teacher_app.auth import service as auth_service
from teacher_app.storage import providers


ROOT = Path(__file__).parents[1]


class RenderWorkerSchemeBTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "jobs.sqlite"
        self.worker_runtime = pgy_app.app.extensions["teacher_worker_web_runtime"]
        connection_patch = patch.object(self.worker_runtime, "connection_factory", self.connect)
        connection_patch.start()
        self.addCleanup(connection_patch.stop)

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
        conn, kind = self.connect()
        try:
            schema_migrations._b_free_local_worker_67(conn, kind)
        finally:
            conn.close()

    def test_web_entrypoint_never_starts_worker(self):
        source = ROOT.joinpath("run_web.sh").read_text(encoding="utf-8")
        self.assertIn("pgy_app:app", source)
        self.assertNotIn("material_worker.py", source)
        self.assertNotIn("worker_pid", source)

    def test_render_blueprint_is_free_web_only(self):
        source = ROOT.joinpath("render.yaml").read_text(encoding="utf-8")
        self.assertIn("type: web", source)
        self.assertIn("plan: free", source)
        self.assertNotIn("type: worker", source)
        self.assertNotIn("biochemical-training-material-worker", source)
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
                headers={"Origin": "http://localhost"},
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
                headers={"Origin": "http://localhost"},
            )
        self.assertEqual(response.status_code, 400)
        cleanup.assert_called_once_with(staging)

    def test_worker_rejects_sha_and_size_mismatch(self):
        source = Path(self.temp.name) / "lesson.txt"
        source.write_text("safe learning material", encoding="utf-8")
        base_job = {"payload": {"originalName": "lesson.txt"}, "sourceBytes": source.stat().st_size, "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        self.assertEqual(material_worker.validate_download(source, {"originalName": "lesson.txt", **base_job}), "lesson.txt")
        with self.assertRaisesRegex(RuntimeError, "大小不符"):
            material_worker.validate_download(source, {"originalName": "lesson.txt", **base_job, "sourceBytes": 1})
        with self.assertRaisesRegex(RuntimeError, "SHA256"):
            material_worker.validate_download(source, {"originalName": "lesson.txt", **base_job, "sourceSha256": "0" * 64})

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

    def test_worker_token_required_and_invalid_rejected(self):
        client = pgy_app.app.test_client()
        with patch.dict(os.environ, {"MATERIAL_WORKER_TOKEN": "worker-secret"}):
            self.assertEqual(client.post("/api/material-worker/claim", json={"workerId": "w1"}).status_code, 401)
            self.assertEqual(client.post("/api/material-worker/claim", json={"workerId": "w1"}, headers={"Authorization": "Bearer wrong"}).status_code, 401)

    def test_claim_is_atomic_and_heartbeat_is_owned(self):
        self.with_queue()
        appmod.create_material_job(job_id="claim-once", payload={"originalName": "lesson.txt"}, staging_backend="local", staging_key="", staging_path=str(Path(self.temp.name) / "missing"), source_sha256="a" * 64, source_bytes=1, material_id="m-claim", original_name="lesson.txt")
        client = pgy_app.app.test_client(); headers = {"Authorization": "Bearer worker-secret"}
        with patch.dict(os.environ, {"MATERIAL_WORKER_TOKEN": "worker-secret"}), patch.object(
            self.worker_runtime, "cleanup_budget_state", return_value=None
        ):
            first = client.post("/api/material-worker/claim", json={"workerId": "worker-a", "capabilities": {}}, headers=headers)
            second = client.post("/api/material-worker/claim", json={"workerId": "worker-b", "capabilities": {}}, headers=headers)
            self.assertEqual(first.status_code, 200); self.assertEqual(second.status_code, 200)
            self.assertEqual(first.get_json()["job"]["id"], "claim-once")
            self.assertIsNone(second.get_json()["job"])
            heartbeat = client.post("/api/material-worker/claim-once/heartbeat", json={"workerId": "worker-a", "capabilities": {"ffmpeg": {"available": True}}}, headers=headers)
        self.assertEqual(heartbeat.status_code, 200)

    def test_compatible_small_upload_download_is_worker_owned(self):
        self.with_queue()
        source = Path(self.temp.name) / "staging" / "lesson.txt"
        source.parent.mkdir(); source.write_text("small compatible upload", encoding="utf-8")
        appmod.create_material_job(job_id="small-source", payload={"originalName": "lesson.txt"}, staging_backend="local", staging_key="", staging_path=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), source_bytes=source.stat().st_size, material_id="m-small", original_name="lesson.txt")
        client = pgy_app.app.test_client(); headers = {"Authorization": "Bearer worker-secret"}
        with patch.dict(os.environ, {"MATERIAL_WORKER_TOKEN": "worker-secret"}), patch.object(
            self.worker_runtime, "cleanup_budget_state", return_value=None
        ):
            claim = client.post("/api/material-worker/claim", json={"workerId": "worker-a"}, headers=headers)
            self.assertEqual(claim.status_code, 200)
            self.assertEqual(claim.get_json()["job"]["downloadPath"], "/api/material-worker/small-source/source")
            denied = client.get("/api/material-worker/small-source/source", headers=headers)
            self.assertEqual(denied.status_code, 400)
            fetched = client.get("/api/material-worker/small-source/source", headers={**headers, "X-Teacher-Worker-Id": "worker-a"})
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.data, source.read_bytes())
        fetched.close()

    def test_worker_complete_deletes_staging_and_retry_retains_it(self):
        self.with_queue()
        appmod.create_material_job(job_id="complete-job", payload={"originalName": "lesson.txt", "materialId": "m-complete"}, staging_backend="r2", staging_key="_staging/material-jobs/complete-job/source.txt", staging_path="", source_sha256="a" * 64, source_bytes=1, material_id="m-complete", original_name="lesson.txt")
        appmod._update_material_job("complete-job", status="processing", worker_id="worker-a")
        client = pgy_app.app.test_client(); headers = {"Authorization": "Bearer worker-secret"}
        with patch.dict(os.environ, {"MATERIAL_WORKER_TOKEN": "worker-secret"}), patch.object(
            self.worker_runtime, "commit_result", return_value={"id": "m-complete"}
        ), patch.object(self.worker_runtime, "delete_staging") as deleted, patch.object(
            self.worker_runtime, "sync_media_processing_metadata", return_value=None
        ):
            complete = client.post("/api/material-worker/complete-job/complete", json={"workerId": "worker-a", "result": {"storageBackend": "mega", "storageKey": "/materials/m-complete/source.txt"}}, headers=headers)
        self.assertEqual(complete.status_code, 200, complete.get_data(as_text=True)); deleted.assert_called_once()
        self.assertEqual(appmod.get_material_job("complete-job")["status"], "completed")

    def test_direct_upload_missing_r2_is_graceful(self):
        client = pgy_app.app.test_client()
        actor = {"username": "admin", "role": "system_admin", "roles": ["system_admin"], "preferredGroup": "grpBio"}
        with patch.object(auth_service, "current_user", return_value=actor), patch.dict(
            os.environ, {"MATERIAL_DIRECT_UPLOAD_ENABLED": "true"}
        ), patch.object(providers, "r2_is_configured", return_value=False):
            response = client.post("/api/material-upload/init", json={"filename": "movie.mp4", "size": 100, "sha256": "a" * 64}, headers={"Origin": "http://localhost"})
        self.assertEqual(response.status_code, 409)

    def test_r2_multipart_init_and_complete_creates_single_runnable_job(self):
        self.with_queue()
        class FakeR2:
            def create_multipart_upload(self, **_kwargs): return {"UploadId": "remote-upload"}
            def generate_presigned_url(self, _operation, Params, ExpiresIn): return f"https://r2.example/{Params.get('PartNumber', 'get')}?expires={ExpiresIn}"
            def complete_multipart_upload(self, **_kwargs): return {}
            def head_object(self, **_kwargs): return {"ContentLength": 20 * 1024 * 1024, "Metadata": {"sha256": "a" * 64}}
            def abort_multipart_upload(self, **_kwargs): return {}
            def delete_object(self, **_kwargs): return {}
        client = pgy_app.app.test_client(); headers = {"Origin": "http://localhost"}
        actor = {"username": "admin", "role": "system_admin", "roles": ["system_admin"], "preferredGroup": "grpBio"}
        r2 = FakeR2()
        with patch.object(auth_service, "current_user", return_value=actor), patch.dict(
            os.environ,
            {"MATERIAL_DIRECT_UPLOAD_ENABLED": "true", "MATERIAL_DIRECT_UPLOAD_MAX_MB": "2048"},
        ), patch.object(providers, "r2_is_configured", return_value=True), patch.object(
            providers, "r2_client", return_value=r2
        ), patch.object(providers, "R2_BUCKET_NAME", "bucket"), patch.object(
            self.worker_runtime, "release_reservation", return_value=None
        ), patch.object(self.worker_runtime, "record_r2_object", return_value=None), patch.object(
            self.worker_runtime, "record_r2_deleted", return_value=None
        ), patch.object(self.worker_runtime, "sync_media_processing_metadata", return_value=None):
            init = client.post("/api/material-upload/init", json={"filename": "movie.mp4", "size": 20 * 1024 * 1024, "sha256": "a" * 64, "partSizeMb": 8}, headers=headers)
            self.assertEqual(init.status_code, 201, init.get_data(as_text=True))
            data = init.get_json(); self.assertEqual(len(data["parts"]), 3)
            self.assertNotIn("secret", str(data).lower())
            malformed = client.post(f"/api/material-upload/{data['uploadId']}/complete", json={"parts": []}, headers=headers)
            self.assertEqual(malformed.status_code, 400)
            complete = client.post(f"/api/material-upload/{data['uploadId']}/complete", json={"parts": [{"partNumber": n, "etag": f'etag-{n}'} for n in range(1, 4)]}, headers=headers)
        self.assertEqual(complete.status_code, 202, complete.get_data(as_text=True))
        self.assertEqual(appmod.get_material_job(data["jobId"])["stagingBackend"], "r2")

    def test_r2_metadata_boundary_is_ascii_safe_for_user_values(self):
        source = Path(self.temp.name) / "source.pptx"
        source.write_bytes(b"pptx")
        captured = {}

        class FakeR2:
            def upload_file(self, *_args, **kwargs):
                captured.update(kwargs)

        metadata = {
            "filename": "2026 生化教育訓練檢驗流程一致性.pptx",
            "title": "教育訓練資料.pptx",
            "description": "교육자료.pptx",
            "category": "training material 2026.pptx",
            "courseTitle": "training (final).pptx 教材📘.pptx",
        }
        with patch.object(appmod, "r2_client", return_value=FakeR2()), patch.object(appmod, "R2_BUCKET_NAME", "bucket"), patch.object(appmod, "r2_record_object"):
            appmod.r2_put_file(source, "_staging/material-jobs/job-safe/source.pptx", metadata=metadata)
        sent = captured["ExtraArgs"]["Metadata"]
        self.assertEqual(set(sent), set(metadata))
        self.assertTrue(all(key.isascii() and value.isascii() for key, value in sent.items()))
        self.assertNotEqual(sent["filename"], metadata["filename"])
        self.assertEqual(sent["category"], "training material 2026.pptx")
        self.assertEqual(sent["courseTitle"].split()[0], "training")

    def test_r2_staging_keeps_unicode_filename_out_of_object_metadata(self):
        source = Path(self.temp.name) / "source.pptx"
        source.write_bytes(b"pptx")
        captured = {}

        class FakeR2:
            def upload_file(self, *_args, **kwargs):
                captured.update(kwargs)

        original = "2026 生化教育訓練檢驗流程一致性.pptx"
        with patch.object(appmod, "shared_staging_backend", return_value="r2"), patch.object(appmod, "r2_large_file", return_value=False), patch.object(appmod, "r2_client", return_value=FakeR2()), patch.object(appmod, "R2_BUCKET_NAME", "bucket"), patch.object(appmod, "r2_record_object"):
            backend, key, staging_path = appmod.upload_material_job_staging(source, "matjob-0123456789abcdef", original)
        sent = captured["ExtraArgs"]["Metadata"]
        self.assertEqual((backend, staging_path), ("r2", ""))
        self.assertEqual(key, "_staging/material-jobs/matjob-0123456789abcdef/source.pptx")
        self.assertNotIn("originalname", sent)
        self.assertTrue(all(value.isascii() for value in sent.values()))

    def test_r2_multipart_unicode_names_are_persisted_outside_metadata(self):
        self.with_queue()
        filenames = (
            "2026 生化教育訓練檢驗流程一致性.pptx",
            "教育訓練資料.pptx",
            "교육자료.pptx",
            "training material 2026.pptx",
            "training (final).pptx",
            "教材📘.pptx",
        )
        size = 8 * 1024 * 1024

        class FakeR2:
            def __init__(self):
                self.multipart_calls = []
                self.uploads = 0

            def create_multipart_upload(self, **kwargs):
                self.multipart_calls.append(kwargs)
                self.uploads += 1
                return {"UploadId": f"remote-upload-{self.uploads}"}

            def generate_presigned_url(self, _operation, Params, ExpiresIn):
                return f"https://r2.example/{Params.get('PartNumber', 'get')}?expires={ExpiresIn}"

            def complete_multipart_upload(self, **_kwargs):
                return {}

            def head_object(self, **_kwargs):
                return {"ContentLength": size, "Metadata": {"sha256": "a" * 64}}

            def abort_multipart_upload(self, **_kwargs):
                return {}

            def delete_object(self, **_kwargs):
                return {}

        r2 = FakeR2()
        client = pgy_app.app.test_client()
        headers = {"Origin": "http://localhost"}
        actor = {"username": "admin", "role": "system_admin", "roles": ["system_admin"], "preferredGroup": "grpBio"}
        with patch.object(auth_service, "current_user", return_value=actor), patch.dict(
            os.environ,
            {"MATERIAL_DIRECT_UPLOAD_ENABLED": "true", "MATERIAL_DIRECT_UPLOAD_MAX_MB": "2048"},
        ), patch.object(providers, "r2_is_configured", return_value=True), patch.object(
            providers, "r2_client", return_value=r2
        ), patch.object(providers, "R2_BUCKET_NAME", "bucket"), patch.object(
            self.worker_runtime, "release_reservation", return_value=None
        ), patch.object(self.worker_runtime, "record_r2_object", return_value=None), patch.object(
            self.worker_runtime, "record_r2_deleted", return_value=None
        ), patch.object(self.worker_runtime, "sync_media_processing_metadata", return_value=None):
            for filename in filenames:
                init = client.post("/api/material-upload/init", json={"filename": filename, "size": size, "sha256": "a" * 64, "partSizeMb": 8}, headers=headers)
                self.assertEqual(init.status_code, 201, init.get_data(as_text=True))
                data = init.get_json()
                metadata = r2.multipart_calls[-1]["Metadata"]
                self.assertNotIn("originalname", metadata)
                self.assertTrue(all(key.isascii() and value.isascii() for key, value in metadata.items()))
                self.assertRegex(r2.multipart_calls[-1]["Key"], r"^_staging/material-jobs/matjob-[0-9a-f]{16}/source\.pptx$")
                conn, _ = self.connect()
                try:
                    session = conn.execute("SELECT original_name,payload FROM material_upload_sessions WHERE id=?", (data["uploadId"],)).fetchone()
                finally:
                    conn.close()
                self.assertEqual(session["original_name"], filename)
                self.assertEqual(json.loads(session["payload"])["originalName"], filename)
                complete = client.post(f"/api/material-upload/{data['uploadId']}/complete", json={"parts": [{"partNumber": 1, "etag": "etag-1"}]}, headers=headers)
                self.assertEqual(complete.status_code, 202, complete.get_data(as_text=True))
                job = appmod.get_material_job(data["jobId"], include_payload=True)
                self.assertEqual(job["originalName"], filename)
                self.assertEqual(job["payload"]["originalName"], filename)
            with patch.dict(os.environ, {"MATERIAL_WORKER_TOKEN": "worker-secret"}), patch.object(
                self.worker_runtime, "cleanup_budget_state", return_value=None
            ):
                claimed = client.post("/api/material-worker/claim", json={"workerId": "unicode-worker"}, headers={"Authorization": "Bearer worker-secret"})
        self.assertEqual(claimed.status_code, 200, claimed.get_data(as_text=True))
        self.assertEqual(claimed.get_json()["job"]["originalName"], filenames[0])
        self.assertEqual(claimed.get_json()["job"]["payload"]["originalName"], filenames[0])

    def test_local_worker_has_no_production_database_client(self):
        source = ROOT.joinpath("material_worker.py").read_text(encoding="utf-8")
        self.assertIn("TEACHER_BASE_URL", source)
        self.assertIn("Authorization", source)
        self.assertNotIn("psycopg", source)
        self.assertNotIn("_db_conn", source)

    def test_b_free_migration_repeats_safely(self):
        self.with_queue()
        conn, kind = self.connect()
        try:
            schema_migrations._b_free_local_worker_67(conn, kind)
            self.assertTrue(conn.execute("SELECT name FROM sqlite_master WHERE name='material_upload_sessions'").fetchone())
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
