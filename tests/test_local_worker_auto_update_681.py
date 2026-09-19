import datetime as dt
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask

ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as appmod
import material_worker
import schema_migrations
from teacher_app.worker import operations as worker_operations
from teacher_app.worker.routes import register_free_worker
from teacher_app.worker.schema import init_schema as init_worker_schema
from teacher_app.worker.web_runtime import WorkerWebRuntime


class LocalWorkerAutoUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_safe_updater_is_origin_main_ff_only_and_never_handles_secrets(self):
        source = ROOT.joinpath("update_material_worker.ps1").read_text(encoding="utf-8")
        self.assertIn("git fetch origin main", source)
        self.assertIn("git pull --ff-only origin main", source)
        self.assertIn("branch -ne \"main\"", source)
        self.assertIn("merge-base --is-ancestor HEAD origin/main", source)
        self.assertIn("working tree is dirty", source)
        self.assertIn("Already up to date", source)
        self.assertNotIn("reset --hard", source)
        self.assertNotIn("git stash", source.lower())
        self.assertNotIn("set-url", source)
        for secret in ("MATERIAL_WORKER_TOKEN", "MEGA_PASSWORD", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN", "R2_SECRET"):
            self.assertNotIn(secret, source)

    def test_autostart_falls_back_and_limits_crash_restarts(self):
        source = ROOT.joinpath("run_material_worker_autostart.ps1").read_text(encoding="utf-8")
        self.assertIn("Safe update did not run; starting the existing local Worker version", source)
        self.assertIn("$workerExit -eq 75", source)
        self.assertIn("$maxCrashRestarts = 5", source)
        self.assertIn("Start-Sleep -Seconds 5", source)
        self.assertIn("Get-FileHash", source)
        self.assertIn("-m pip install -r", source)
        self.assertIn("FFmpeg=$ffmpeg", source)
        self.assertIn("MEGAcmd=$mega", source)

    def test_idle_check_respects_minimum_interval_and_requests_restart_after_update(self):
        state = Path(self.temp.name) / "state.json"
        runner = Mock(return_value=0)
        with patch.dict(os.environ, {"MATERIAL_WORKER_AUTO_UPDATE": "true", "MATERIAL_WORKER_UPDATE_INTERVAL_HOURS": "0", "MATERIAL_WORKER_UPDATE_STATE_PATH": str(state)}, clear=False), patch.object(material_worker, "worker_metadata", side_effect=[{"workerSha": "aaaaaaa"}, {"workerSha": "bbbbbbb"}]):
            controller = material_worker.AutoUpdateController(root=self.temp.name, runner=runner, now=lambda: "2026-09-15T12:00:00+00:00")
            self.assertEqual(controller.interval_seconds, 3600)
            self.assertTrue(controller.check_when_idle())
        runner.assert_called_once()
        self.assertTrue(controller.update_available)
        self.assertIn("lastUpdateCheckAt", state.read_text(encoding="utf-8"))

    def test_processing_job_never_invokes_auto_update(self):
        api = Mock()
        api.post.return_value = {"job": {"id": "active"}}
        updater = Mock(); updater.metadata.return_value = {}; updater.check_when_idle.return_value = True
        caps = {"ffmpeg": {"available": True}, "ffprobe": {"available": True}, "libreOffice": {"available": True}}
        with patch.object(material_worker, "WorkerApi", return_value=api), patch.object(material_worker, "AUTO_UPDATER", updater), patch.object(material_worker, "capability", return_value=caps), patch.object(material_worker, "process_one", side_effect=KeyboardInterrupt):
            self.assertEqual(material_worker.main(), 0)
        updater.check_when_idle.assert_not_called()

    def test_idle_update_exits_only_with_restart_code(self):
        api = Mock()
        api.post.return_value = {"job": None}
        updater = Mock(); updater.metadata.return_value = {}; updater.check_when_idle.return_value = True
        caps = {"ffmpeg": {"available": True}, "ffprobe": {"available": True}, "libreOffice": {"available": True}}
        with patch.object(material_worker, "WorkerApi", return_value=api), patch.object(material_worker, "AUTO_UPDATER", updater), patch.object(material_worker, "capability", return_value=caps):
            self.assertEqual(material_worker.main(), material_worker.RESTART_FOR_UPDATE)

    def test_heartbeat_payload_has_build_metadata_and_no_secret_fields(self):
        captured = {}
        api = object.__new__(material_worker.WorkerApi)
        with patch.object(api, "post", side_effect=lambda _path, body: captured.update(body) or {}), patch.object(material_worker, "capability", return_value={"ffmpeg": {"available": True}}), patch.object(material_worker.AUTO_UPDATER, "metadata", return_value={"workerVersion": "6.8.1", "workerSha": "d78069c", "workerBranch": "main", "updateAvailable": False, "lastUpdateCheckAt": "2026-09-15T12:00:00+00:00"}):
            api.heartbeat()
        self.assertEqual(captured["workerVersion"], "6.8.1")
        self.assertEqual(captured["workerSha"], "d78069c")
        self.assertEqual(captured["workerBranch"], "main")
        self.assertNotIn("MATERIAL_WORKER_TOKEN", captured)
        self.assertNotIn("MEGA_PASSWORD", captured)

    def test_web_safely_preserves_and_exposes_worker_build_metadata(self):
        db = Path(self.temp.name) / "jobs.sqlite"
        def connect():
            conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row; conn.isolation_level = None
            return conn, "sqlite"
        conn, kind = connect()
        try:
            init_worker_schema(conn, kind)
            schema_migrations._b_free_local_worker_67(conn, kind)
        finally:
            conn.close()
        runtime = WorkerWebRuntime(
            cleanup_budget_state=lambda: None,
            enforce_large_upload_budget=lambda *_args: None,
            release_reservation=lambda *_args: None,
            budget_status=lambda: {},
            download_staging=lambda *_args: None,
            delete_staging=lambda *_args: None,
            commit_result=lambda _job, result: result,
            sync_media_processing_metadata=lambda *_args: None,
            connection_factory=connect,
            worker_token="worker-secret",
        )
        web = Flask("worker-build-metadata")
        web.config.update(TESTING=True, SECRET_KEY="test")
        register_free_worker(web, runtime=runtime)
        response = web.test_client().post("/api/material-worker/heartbeat", json={"workerId": "worker-a", "capabilities": {"ffmpeg": {"available": True}, "libreOffice": {"available": True}}, "workerVersion": "6.8.1", "workerSha": "d78069c", "workerBranch": "main", "updateAvailable": True, "lastUpdateCheckAt": "2026-09-15T12:00:00+00:00", "MEGA_PASSWORD": "must-not-store"}, headers={"Authorization": "Bearer worker-secret"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        with patch("teacher_app.worker.operations.r2_budget.status", return_value={}):
            worker = worker_operations.status(lambda: {}, connection_factory=connect)["workers"][0]
        self.assertEqual(worker["workerVersion"], "6.8.1")
        self.assertEqual(worker["workerSha"], "d78069c")
        self.assertEqual(worker["workerBranch"], "main")
        self.assertTrue(worker["updateAvailable"])
        self.assertNotIn("MEGA_PASSWORD", str(worker))

    def test_env_and_render_worker_boundary_remain_safe(self):
        self.assertIn(".local-worker.env", ROOT.joinpath(".gitignore").read_text(encoding="utf-8"))
        render = ROOT.joinpath("render.yaml").read_text(encoding="utf-8")
        self.assertIn("MATERIAL_WORKER_ENABLED", render)
        self.assertNotIn("type: worker", render)


if __name__ == "__main__":
    unittest.main()
