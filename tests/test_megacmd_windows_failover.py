import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app as appmod


ROOT = Path(__file__).parents[1]


class MegaCmdWindowsTests(unittest.TestCase):
    def test_windows_path_includes_official_megacmd_location(self):
        env = {"PATH": r"C:\Windows\System32", "ProgramFiles": r"C:\Program Files"}
        with patch.object(appmod.sys, "platform", "win32"), patch.dict(os.environ, env, clear=False):
            path = appmod._megacmd_path(env)
        self.assertEqual(path.split(";")[0], r"C:\Program Files\MEGAcmd")
        self.assertIn(r"C:\Windows\System32", path)

    def test_windows_batch_wrapper_uses_subprocess_quoting(self):
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        wrapper = r"C:\Program Files\MEGAcmd\mega-put.bat"
        command = [wrapper, "-c", r"C:\safe folder\source.pptx", "/materials"]
        with patch.object(appmod.sys, "platform", "win32"), patch.object(appmod, "_megacmd_find", return_value=wrapper), patch.object(appmod.subprocess, "run", return_value=completed) as run:
            result = appmod._mega_run(["mega-put", "-c", r"C:\safe folder\source.pptx", "/materials"])
        self.assertIs(result, completed)
        self.assertEqual(run.call_args.args[0], command)
        self.assertTrue(run.call_args.kwargs["shell"])
        self.assertFalse(run.call_args.kwargs["check"])

    def test_native_megacmd_executable_keeps_argv_without_shell(self):
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        executable = r"C:\Program Files\MEGAcmd\mega-put.exe"
        with patch.object(appmod.sys, "platform", "win32"), patch.object(appmod, "_megacmd_find", return_value=executable), patch.object(appmod.subprocess, "run", return_value=completed) as run:
            appmod._mega_run(["mega-put", "-c", "source.pptx", "/materials"])
        self.assertEqual(run.call_args.args[0], [executable, "-c", "source.pptx", "/materials"])
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_bat_resolution_counts_as_configured_megacmd(self):
        with patch.object(appmod, "MEGA_EMAIL", "teacher@example.test"), patch.object(appmod, "MEGA_PASSWORD", "secret"), patch.object(appmod, "_megacmd_find", side_effect=[r"C:\MEGAcmd\mega-whoami.bat", r"C:\MEGAcmd\mega-put.bat"]):
            self.assertTrue(appmod.mega_is_configured())

    def test_auto_storage_does_not_hide_missing_megacmd(self):
        with patch.object(appmod, "MATERIAL_STORAGE_BACKEND", "auto"), patch.object(appmod, "MEGA_EMAIL", "teacher@example.test"), patch.object(appmod, "MEGA_PASSWORD", "secret"), patch.object(appmod, "mega_is_configured", return_value=False), patch.object(appmod, "gdrive_is_configured", return_value=True), patch.object(appmod, "oci_is_configured", return_value=False), patch.object(appmod, "r2_is_configured", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "不會自動改用 Google Drive"):
                appmod.active_material_backend()

    def test_command_error_is_reported_and_is_not_capacity(self):
        completed = SimpleNamespace(returncode=2, stdout="", stderr="authentication failed")
        with patch.object(appmod, "_megacmd_find", return_value="mega-login"), patch.object(appmod.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "MEGAcmd 執行失敗"):
                appmod._mega_run(["mega-login", "teacher@example.test", "bad-password"])
        self.assertFalse(appmod._is_mega_capacity_full_error(RuntimeError("MEGA 登入失敗：authentication failed")))


class MegaFailoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source.pptx"
        self.source.write_bytes(b"pptx")

    def test_capacity_classifier_is_specific_to_capacity(self):
        self.assertTrue(appmod._is_mega_capacity_full_error(RuntimeError("Storage quota exceeded")))
        self.assertTrue(appmod._is_mega_capacity_full_error(RuntimeError("免費模式已鎖定")))
        self.assertFalse(appmod._is_mega_capacity_full_error(RuntimeError("MEGA 登入失敗：authentication failed")))
        self.assertFalse(appmod._is_mega_capacity_full_error(RuntimeError("MEGAcmd 執行失敗 (mega-put)：network error")))

    def test_gdrive_failover_requires_flag_backend_and_connection(self):
        with patch.object(appmod, "STORAGE_FAILOVER_ON_FULL", True), patch.object(appmod, "STORAGE_FALLBACK_BACKEND", "gdrive"), patch.object(appmod, "gdrive_is_configured", return_value=True):
            self.assertEqual(appmod._mega_gdrive_failover_ready(), "gdrive")
        with patch.object(appmod, "STORAGE_FAILOVER_ON_FULL", False), patch.object(appmod, "STORAGE_FALLBACK_BACKEND", "gdrive"), patch.object(appmod, "gdrive_is_configured", return_value=True):
            self.assertEqual(appmod._mega_gdrive_failover_ready(), "")
        with patch.object(appmod, "STORAGE_FAILOVER_ON_FULL", True), patch.object(appmod, "STORAGE_FALLBACK_BACKEND", "r2"), patch.object(appmod, "gdrive_is_configured", return_value=True):
            self.assertEqual(appmod._mega_gdrive_failover_ready(), "")

    def test_normal_mega_staging_never_calls_gdrive(self):
        with patch.object(appmod, "shared_staging_backend", return_value="mega"), patch.object(appmod, "_mega_free_guard"), patch.object(appmod, "_mega_root_id", return_value="/root"), patch.object(appmod, "_mega_upload_file", return_value="/root/_staging/material-jobs/job/source.pptx"), patch.object(appmod, "gdrive_upload_file") as gdrive:
            backend, key, staging_path = appmod.upload_material_job_staging(self.source, "job", "lesson.pptx")
        self.assertEqual((backend, key, staging_path), ("mega", "/root/_staging/material-jobs/job/source.pptx", ""))
        gdrive.assert_not_called()

    def test_capacity_full_staging_uses_enabled_gdrive_only(self):
        with patch.object(appmod, "shared_staging_backend", return_value="mega"), patch.object(appmod, "_mega_free_guard", side_effect=RuntimeError("Storage quota exceeded")), patch.object(appmod, "_mega_gdrive_failover_ready", return_value="gdrive"), patch.object(appmod, "_gdrive_staging_parent", return_value="parent"), patch.object(appmod, "gdrive_upload_file", return_value={"id": "gdrive-source"}) as gdrive:
            backend, key, staging_path = appmod.upload_material_job_staging(self.source, "job", "lesson.pptx")
        self.assertEqual((backend, key, staging_path), ("gdrive", "gdrive-source", ""))
        gdrive.assert_called_once()

    def test_login_or_command_error_does_not_fallback(self):
        with patch.object(appmod, "shared_staging_backend", return_value="mega"), patch.object(appmod, "_mega_free_guard", side_effect=RuntimeError("MEGA 登入失敗：authentication failed")), patch.object(appmod, "_mega_gdrive_failover_ready", return_value="gdrive"), patch.object(appmod, "gdrive_upload_file") as gdrive:
            with self.assertRaisesRegex(RuntimeError, "MEGA 登入失敗"):
                appmod.upload_material_job_staging(self.source, "job", "lesson.pptx")
        gdrive.assert_not_called()

    def test_worker_powershell_path_update_is_process_local(self):
        source = ROOT.joinpath("run_material_worker.ps1").read_text(encoding="utf-8")
        self.assertIn("MEGAcmd", source)
        self.assertIn("$env:Path", source)
        self.assertIn("ProgramFiles", source)
        self.assertNotIn("setx", source.lower())


if __name__ == "__main__":
    unittest.main()
