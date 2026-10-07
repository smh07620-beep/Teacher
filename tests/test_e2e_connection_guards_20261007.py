"""Guards for the 'features exist but do not connect' tooling (items 1-6)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from teacher_app.worker import doctor, operations, site_check  # noqa: E402
import check_kokoro_voices  # noqa: E402
import production_synthetic  # noqa: E402
import production_worker_check as pwc  # noqa: E402
from teacher_app.materials import media_audio_runtime  # noqa: E402


class SiteCheckTests(unittest.TestCase):
    def test_commit_prefix_match(self):
        self.assertTrue(site_check.commits_match("abcdef1", "abcdef1234567890"))
        self.assertFalse(site_check.commits_match("abcdef1", "abcdef2234"))
        self.assertFalse(site_check.commits_match("abc", "abc"))

    def test_compare_states(self):
        def health(version, commit):
            return {"payload": {"version": version, "deployment": {"commit": commit}}}

        self.assertEqual(site_check.compare({"version": "1", "sha": "abcdef123456"}, health("1", "abcdef12345"))["state"], "match")
        self.assertEqual(site_check.compare({"version": "1", "sha": "abcdef123456"}, health("2", "abcdef123456"))["state"], "version_mismatch")
        self.assertEqual(site_check.compare({"version": "1", "sha": "1111111"}, health("1", "2222222"))["state"], "commit_differs")
        self.assertEqual(site_check.compare({"version": "1"}, {"error": "x"})["state"], "site_unreachable")

    def test_monitor_caches_and_logs_state_changes(self):
        calls, logs, now = [], [], [0.0]

        def checker(_url):
            calls.append(1)
            return {"state": "match", "message": "ok"}

        monitor = site_check.SiteVersionMonitor("https://x", interval_seconds=600, log=logs.append, checker=checker, clock=lambda: now[0])
        monitor.snapshot()
        monitor.snapshot()
        self.assertEqual(len(calls), 1)
        now[0] = 601
        monitor.snapshot()
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(logs), 1)  # only the first state change is logged

    def test_checker_exception_never_breaks_heartbeat(self):
        def boom(_url):
            raise RuntimeError("x")

        snap = site_check.SiteVersionMonitor("https://x", checker=boom).snapshot()
        self.assertEqual(snap["state"], "unknown")

    def test_operations_projection(self):
        self.assertEqual(operations._site_version_projection({"siteVersionCheck": {"state": "commit_differs", "message": "m"}})["siteVersionState"], "commit_differs")
        self.assertEqual(operations._site_version_projection({})["siteVersionState"], "")

    def test_workers_publish_the_check_in_heartbeat(self):
        for name in ("material_worker.py", "ai_question_worker.py"):
            self.assertIn("siteVersionCheck", (ROOT / name).read_text(encoding="utf-8"), name)


class DoctorTests(unittest.TestCase):
    def _doctor(self, env, status=200):
        def http(method, url, **_kw):
            return status, "{}"

        return doctor.Doctor(env, http=http, quick=True, root=ROOT)

    def test_missing_config_fails(self):
        d = self._doctor({})
        d.check_config()
        self.assertEqual(d.results[0].status, doctor.FAIL)
        self.assertEqual(doctor.Doctor.exit_code(d.results), 1)

    def test_rejected_token_fails_and_good_token_passes(self):
        env = {"TEACHER_BASE_URL": "https://example.test", "MATERIAL_WORKER_TOKEN": "t"}
        bad = self._doctor(env, 401)
        bad.check_tokens()
        self.assertTrue(all(r.status == doctor.FAIL for r in bad.results))
        good = self._doctor(env, 404)
        good.check_tokens()
        self.assertTrue(all(r.status == doctor.OK for r in good.results))

    def test_env_file_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.env"
            path.write_text("# c\nA=1\n B = two \n", encoding="utf-8")
            env = {}
            doctor.load_env_file(path, env)
            self.assertEqual(env, {"A": "1", "B": "two"})

    def test_env_file_loader_ignores_utf8_bom_on_first_key(self):
        # Notepad/PowerShell often save a BOM; the first key must still be read.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.env"
            path.write_bytes(b"\xef\xbb\xbfTEACHER_BASE_URL=https://example.test\nB=2\n")
            env = {}
            doctor.load_env_file(path, env)
            self.assertEqual(env, {"TEACHER_BASE_URL": "https://example.test", "B": "2"})

    def test_doctor_entry_loads_env_file_before_storage_module_import(self):
        # providers.py captures R2_* once at import; the entry script must load
        # the env file first or configured R2 is reported as "not set".
        import subprocess, sys
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.env"
            path.write_bytes(b"\xef\xbb\xbfR2_BUCKET_NAME=bucket-x\nR2_ACCOUNT_ID=acct\nR2_ACCESS_KEY_ID=k\nR2_SECRET_ACCESS_KEY=s\n")
            code = (
                "import sys; root=sys.argv[2]; env=sys.argv[1]; sys.argv=['worker_doctor.py','--env-file',env]; "
                "sys.path.insert(0, root); "
                "import worker_doctor; from teacher_app.storage import providers; "
                "print(providers.R2_BUCKET_NAME, providers.R2_ACCOUNT_ID, providers.R2_ACCESS_KEY_ID, providers.R2_SECRET_ACCESS_KEY)"
            )
            out = subprocess.run(
                [sys.executable, "-I", "-c", code, str(path), str(ROOT)],
                cwd=str(ROOT), capture_output=True, text=True, timeout=120,
                env={k: v for k, v in __import__("os").environ.items() if not k.startswith(("R2_", "MEGA_"))} ,
            )
            self.assertEqual(out.stdout.strip().splitlines()[-1], "bucket-x acct k s", out.stderr[-500:])

    def test_bootstrap_runs_doctor(self):
        text = (ROOT / "setup_teacher_worker.ps1").read_text(encoding="utf-8")
        self.assertIn("Invoke-WorkerDoctor", text)
        self.assertIn("worker_doctor.py", text)
        self.assertIn("SkipDoctor", text)


class ProductionCheckTests(unittest.TestCase):
    HEALTHY_JOBS = {"workers": [{"workerId": "w", "status": "online"}]}
    HEALTHY_AUDIO = {"worker": {"online": True, "queues": ["media_audio"], "kokoroInstalled": True}, "providerReady": True, "r2Ready": True, "readyForPreview": True}

    def test_healthy(self):
        result = pwc.evaluate(self.HEALTHY_JOBS, self.HEALTHY_AUDIO)
        self.assertEqual(result["problems"], [])

    def test_offline_workers_are_problems(self):
        result = pwc.evaluate({"workers": []}, {"worker": {"online": False}, "providerReady": True})
        self.assertEqual(len(result["problems"]), 2)

    def test_stale_ai_worker_missing_queue(self):
        audio = {**self.HEALTHY_AUDIO, "worker": {"online": True, "queues": [], "kokoroInstalled": True}}
        self.assertTrue(any("media_audio" in p for p in pwc.evaluate(self.HEALTHY_JOBS, audio)["problems"]))

    def test_version_mismatch_is_warning(self):
        jobs = {"workers": [{"workerId": "w", "status": "online", "siteVersionState": "commit_differs", "siteVersionMessage": "m"}]}
        result = pwc.evaluate(jobs, self.HEALTHY_AUDIO)
        self.assertEqual(result["problems"], [])
        self.assertEqual(len(result["warnings"]), 1)

    def test_skipped_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {}, clear=True):
            import os
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                self.assertEqual(pwc.main(["--base-url", "https://x"]), 0)
                self.assertEqual(production_synthetic.main(["--base-url", "https://x"]), 0)
                self.assertTrue(json.loads(Path("production-synthetic-report.json").read_text())["skipped"])
            finally:
                os.chdir(cwd)

    def test_wav_validation(self):
        class Client:
            def __init__(self, body):
                self.body = body

            def request(self, *a, **k):
                return 200, {}, self.body

        wav = b"RIFF" + b"\0\0\0\0" + b"WAVE" + b"\0" * 4096
        self.assertEqual(production_synthetic._check_wav(Client(wav), "https://r2/x"), len(wav))
        with self.assertRaises(RuntimeError):
            production_synthetic._check_wav(Client(b"<html>" + b"x" * 4096), "https://r2/x")

    def test_synthetic_workflow_is_not_part_of_the_deploy_gate(self):
        for name in ("production-synthetic.yml", "kokoro-voices-check.yml"):
            text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            self.assertIn("schedule:", text)
            self.assertNotIn("pull_request", text)
            self.assertNotIn("push:", text)


class VoiceListTests(unittest.TestCase):
    def test_missing_voice_detected(self):
        files = [f"voices/{v}.pt" for v in media_audio_runtime.ALLOWED_VOICES if v != "zm_012"]
        self.assertEqual(check_kokoro_voices.missing_voices(files), ["zm_012"])
        self.assertEqual(check_kokoro_voices.check(fetcher=lambda _r: files + ["voices/zm_012.pt"])["ok"], True)

    def test_frontend_and_backend_voice_ids_agree(self):
        import re

        known = set(media_audio_runtime.ALLOWED_VOICES) | set(media_audio_runtime.LEGACY_VOICE_ALIASES)
        for base in ("static", "teacher_app"):
            for path in (ROOT / base).rglob("*"):
                if path.suffix not in {".js", ".html", ".py"} or not path.is_file():
                    continue
                for voice in re.findall(r"\bz[fm]_[0-9a-z]+", path.read_text(encoding="utf-8", errors="ignore")):
                    self.assertIn(voice, known, f"{path.relative_to(ROOT)} references unknown voice {voice}")


if __name__ == "__main__":
    unittest.main()
