"""Synthetic check must not report Workers offline during the quiet window (2026-10-26)."""
import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import production_synthetic as ps  # noqa: E402
quiet_hours = ps.quiet_hours


def taipei(hour, minute=0):
    return dt.datetime(2026, 10, 26, hour, minute, tzinfo=quiet_hours.TAIWAN_TZ).astimezone(dt.timezone.utc)


class FakeClient:
    def __init__(self, *_a, **_k):
        self.calls = []

    def login(self, *_a):
        return {"role": "education_admin"}

    def json(self, method, path, **_k):
        self.calls.append(path)
        raise AssertionError("worker endpoints must not be called during quiet hours")


class QuietHoursTests(unittest.TestCase):
    def run_at(self, when):
        real = quiet_hours.in_quiet_hours
        with mock.patch.object(ps, "ProductionClient", FakeClient), \
             mock.patch.dict("os.environ", {"TEACHER_QUIET_HOURS": "01:00-06:00"}), \
             mock.patch.object(ps.quiet_hours, "in_quiet_hours", lambda **k: real(when, **k)):
            return ps.run("https://example.test", "u", "p", group="", voice="v", skip_tts=False, skip_material=False, timeout_seconds=5)

    def test_early_morning_run_is_skipped_not_failed(self):
        for when in (taipei(3, 17), taipei(5, 47), taipei(6, 10)):
            report = self.run_at(when)
            self.assertTrue(report.ok, when)

    def test_daytime_still_checks_workers(self):
        report = self.run_at(taipei(9, 17))
        # FakeClient refuses worker calls, so a daytime run must have tried (and failed) them.
        self.assertFalse(report.ok)
        self.assertEqual(report.steps[1]["name"], "worker-readiness")

    def test_script_runs_without_flask(self):
        """The GitHub runner has only the standard library installed."""
        import subprocess
        code = "import sys, runpy; sys.modules['flask'] = None; sys.argv = ['x', '--help']; runpy.run_path(%r, run_name='__main__')" % str(ROOT / "tools" / "production_synthetic.py")
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr[-500:])

    def test_workflow_scheduled_outside_quiet_window(self):
        text = (ROOT / ".github/workflows/production-synthetic.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "17 1 * * *"', text)


if __name__ == "__main__":
    unittest.main()
