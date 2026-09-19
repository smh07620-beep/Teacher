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

    def test_safe_updater_requires_verified_pinned_release_and_never_tracks_main(self):
        source = ROOT.joinpath("update_material_worker.ps1").read_text(encoding="utf-8")
        self.assertIn("MATERIAL_WORKER_RELEASE_REF", source)
        self.assertIn("MATERIAL_WORKER_RELEASE_COMMIT", source)
        self.assertIn("MATERIAL_WORKER_REQUIRE_SIGNED_TAG", source)
        self.assertIn("git verify-tag", source)
        self.assertIn("refs/tags/", source)
        self.assertIn("git merge --ff-only", source)
        self.assertNotIn("git pull --ff-only origin main", source)
        self.assertNotIn("git fetch origin main", source)
        self.assertIn("working tree is dirty", source)
        self.assertIn("Already on approved release", source)
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
        batch = ROOT.joinpath("run_material_worker.bat").read_text(encoding="utf-8")
        self.assertIn("run_material_worker_autostart.ps1", batch)
        self.assertNotIn("python -u material_worker.py", batch)

    def test_windows_task_installer_serviceizes_worker_without_embedding_secrets(self):
        source = ROOT.joinpath("install_material_worker_task.ps1").read_text(encoding="utf-8")
        for marker in (
            "New-ScheduledTaskTrigger -AtStartup",
            "run_material_worker_autostart.ps1",
            "-WorkingDirectory $root",
            "-RestartCount 5",
            "-RestartInterval (New-TimeSpan -Minutes 1)",
            "-StartWhenAvailable",
            "-LogonType ServiceAccount",
            "-Principal $taskPrincipal",
            "-User $TaskUser",
            "-Password $plainPassword",
            "-RunLevel Highest",
            "Normalize-ServiceAccount",
            "Get-Credential",
            "Register-ScheduledTask",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("-AtLogOn", source)
        self.assertNotIn("-InputObject $task", source)
        self.assertIn("NT AUTHORITY\\SYSTEM", source)
        self.assertNotIn("DOMAIN\\teacher-worker$", source)
        self.assertNotIn("material_worker.py\"", source)

        service_start = source.index("if ($ServiceAccount) {")
        password_start = source.index("} else {", service_start)
        footer_start = source.index("if ($registered) {", password_start)
        service_block = source[service_start:password_start]
        password_block = source[password_start:footer_start]
        self.assertIn("-Principal $taskPrincipal", service_block)
        self.assertNotIn("-User $TaskUser", service_block)
        self.assertNotIn("-Password $plainPassword", service_block)
        self.assertIn("-User $TaskUser", password_block)
        self.assertIn("-Password $plainPassword", password_block)
        self.assertNotIn("-Principal $taskPrincipal", password_block)
        self.assertNotIn("-InputObject $task", password_block)

        for secret in (
            "MATERIAL_WORKER_TOKEN",
            "MEGA_PASSWORD",
            "GDRIVE_CLIENT_SECRET",
            "GDRIVE_REFRESH_TOKEN",
            "R2_SECRET",
        ):
            self.assertNotIn(secret, source)

        docs = ROOT.joinpath("LOCAL_WORKER_6_7.md").read_text(encoding="utf-8")
        self.assertIn("install_material_worker_task.ps1", docs)
        self.assertIn("**At startup**", docs)
        self.assertIn("Run whether", docs)

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

    def test_auto_update_is_disabled_until_explicitly_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            controller = material_worker.AutoUpdateController(root=self.temp.name, runner=Mock())
        self.assertFalse(controller.enabled)
        self.assertFalse(controller.due())

    def test_job_heartbeat_loop_reuses_cached_capabilities(self):
        api = Mock()
        caps = {"ffmpeg": {"available": True}, "libreOffice": {"available": True}}
        heartbeat = material_worker.JobHeartbeat(api, "job-long", capabilities=caps, interval_seconds=5)

        class StopAfterOnePulse:
            def __init__(self): self.calls = 0
            def wait(self, _seconds):
                self.calls += 1
                return self.calls > 1

        heartbeat._stop = StopAfterOnePulse()
        heartbeat._run()
        api.heartbeat.assert_called_once_with("job-long", capabilities=caps)

    def test_job_heartbeat_requires_initial_ownership_pulse(self):
        api = Mock()
        api.heartbeat.side_effect = RuntimeError("Worker API 409: ownership mismatch")
        with self.assertRaisesRegex(RuntimeError, "409"):
            with material_worker.JobHeartbeat(api, "job-lost", capabilities={}):
                self.fail("lost job must not enter processing context")

    def test_completion_ack_retries_transient_failure_without_republish(self):
        api = Mock()
        api.post.side_effect = [RuntimeError("Worker API 503: unavailable"), {"ok": True, "status": "completed"}]
        with patch.object(material_worker.time, "sleep") as sleep:
            result = material_worker.complete_job(api, "job-1", {"storageKey": "remote"})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(api.post.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_completion_ack_does_not_retry_nontransient_worker_api_error(self):
        api = Mock()
        api.post.side_effect = RuntimeError("Worker API 409: ownership mismatch")
        with patch.object(material_worker.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "409"):
                material_worker.complete_job(api, "job-1", {})
        api.post.assert_called_once()
        sleep.assert_not_called()

    def test_worker_documented_env_has_heartbeat_and_pinned_release_settings(self):
        docs = ROOT.joinpath("LOCAL_WORKER_6_7.md").read_text(encoding="utf-8")
        self.assertIn("MATERIAL_WORKER_HEARTBEAT_SECONDS=30", docs)
        self.assertIn("MATERIAL_WORKER_AUTO_UPDATE=false", docs)
        self.assertIn("MATERIAL_WORKER_RELEASE_REF=v6.8.1", docs)
        self.assertIn("MATERIAL_WORKER_REQUIRE_SIGNED_TAG=true", docs)
        self.assertIn(".local-worker.env.example", docs)

        example = ROOT.joinpath(".local-worker.env.example").read_text(encoding="utf-8")
        for marker in (
            "TEACHER_BASE_URL=https://teacher.example.invalid",
            "MATERIAL_WORKER_TOKEN=REPLACE_WITH_RENDER_WORKER_TOKEN",
            "MATERIAL_WORKER_HEARTBEAT_SECONDS=30",
            "MATERIAL_WORKER_AUTO_UPDATE=false",
            "MATERIAL_WORKER_UPDATE_INTERVAL_HOURS=6",
            "MATERIAL_WORKER_RELEASE_REF=v6.8.1",
            "MATERIAL_WORKER_RELEASE_COMMIT=",
            "MATERIAL_WORKER_REQUIRE_SIGNED_TAG=true",
        ):
            self.assertIn(marker, example)
        self.assertNotIn("long-random-secret-from-Render", example)

        gitignore = ROOT.joinpath(".gitignore").read_text(encoding="utf-8")
        self.assertIn(".local-worker.env", gitignore)
        self.assertIn("!.local-worker.env.example", gitignore)

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
        self.assertNotIn("biochemical-training-material-worker", render)
        self.assertIn("biochemical-training-ai-worker", render)
        self.assertIn("python -u ai_question_worker.py", render)


if __name__ == "__main__":
    unittest.main()
