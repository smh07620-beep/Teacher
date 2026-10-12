"""Overnight quiet window for the free Render plan (2026-10-12)."""
import datetime as dt
import unittest
from pathlib import Path
from unittest import mock

from teacher_app.common import quiet_hours
from teacher_app.notifications import reminders

ROOT = Path(__file__).resolve().parents[1]
UTC = dt.timezone.utc


def taipei(hour, minute=0, second=0):
    """A UTC instant that is hour:minute in Taiwan time (UTC+8)."""
    local = dt.datetime(2026, 10, 12, hour, minute, second, tzinfo=quiet_hours.TAIWAN_TZ)
    return local.astimezone(UTC)


class ParseTests(unittest.TestCase):
    def test_valid_specs_and_disabled_values(self):
        self.assertEqual(quiet_hours.parse_quiet_hours("01:00-06:00"), (60, 360))
        self.assertEqual(quiet_hours.parse_quiet_hours(" 23:30 - 05:15 "), (1410, 315))
        for off in ("", "off", "OFF", "none", "0", None):
            self.assertIsNone(quiet_hours.parse_quiet_hours(off), off)
        for bad in ("abc", "25:00-06:00", "01:00", "01:00-01:00", "1-2-3"):
            self.assertIsNone(quiet_hours.parse_quiet_hours(bad), bad)


class WindowTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict("os.environ", {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        import os

        os.environ.pop(quiet_hours.ENV_NAME, None)

    def test_off_by_default_for_callers_without_a_default(self):
        self.assertFalse(quiet_hours.in_quiet_hours(taipei(3)))

    def test_worker_default_covers_01_to_06_taiwan_time(self):
        d = quiet_hours.DEFAULT_WORKER_QUIET_HOURS
        self.assertFalse(quiet_hours.in_quiet_hours(taipei(0, 59), default=d))
        self.assertTrue(quiet_hours.in_quiet_hours(taipei(1, 0), default=d))
        self.assertTrue(quiet_hours.in_quiet_hours(taipei(5, 59), default=d))
        self.assertFalse(quiet_hours.in_quiet_hours(taipei(6, 0), default=d))
        self.assertFalse(quiet_hours.in_quiet_hours(taipei(14, 0), default=d))

    def test_window_that_crosses_midnight(self):
        with mock.patch.dict("os.environ", {quiet_hours.ENV_NAME: "23:00-05:00"}):
            self.assertTrue(quiet_hours.in_quiet_hours(taipei(23, 30)))
            self.assertTrue(quiet_hours.in_quiet_hours(taipei(2)))
            self.assertFalse(quiet_hours.in_quiet_hours(taipei(5)))
            self.assertFalse(quiet_hours.in_quiet_hours(taipei(12)))

    def test_environment_overrides_the_default_and_off_disables_it(self):
        d = quiet_hours.DEFAULT_WORKER_QUIET_HOURS
        with mock.patch.dict("os.environ", {quiet_hours.ENV_NAME: "off"}):
            self.assertFalse(quiet_hours.in_quiet_hours(taipei(3), default=d))
        with mock.patch.dict("os.environ", {quiet_hours.ENV_NAME: "10:00-11:00"}):
            self.assertTrue(quiet_hours.in_quiet_hours(taipei(10, 30), default=d))
            self.assertFalse(quiet_hours.in_quiet_hours(taipei(3), default=d))

    def test_grace_period_extends_the_end(self):
        with mock.patch.dict("os.environ", {quiet_hours.ENV_NAME: "01:00-06:00"}):
            self.assertFalse(quiet_hours.in_quiet_hours(taipei(6, 5)))
            self.assertTrue(quiet_hours.in_quiet_hours(taipei(6, 5), grace_minutes=15))
            self.assertFalse(quiet_hours.in_quiet_hours(taipei(6, 15), grace_minutes=15))

    def test_seconds_until_end_never_oversleeps(self):
        d = quiet_hours.DEFAULT_WORKER_QUIET_HOURS
        self.assertEqual(quiet_hours.seconds_until_quiet_end(taipei(5, 59, 30), default=d), 30)
        self.assertEqual(quiet_hours.seconds_until_quiet_end(taipei(1, 0, 0), default=d), 5 * 3600)
        self.assertEqual(quiet_hours.seconds_until_quiet_end(taipei(12), default=d), 0)

    def test_naive_datetimes_are_treated_as_utc(self):
        d = quiet_hours.DEFAULT_WORKER_QUIET_HOURS
        # 18:00 UTC is 02:00 in Taiwan.
        self.assertTrue(quiet_hours.in_quiet_hours(dt.datetime(2026, 10, 12, 18, 0), default=d))


class AlertsAndWiringTests(unittest.TestCase):
    def test_incident_alerts_are_paused_during_the_window_only_when_configured(self):
        with mock.patch.object(reminders, "_send_operational_alerts", return_value=7) as send:
            with mock.patch.dict("os.environ", {quiet_hours.ENV_NAME: "off"}):
                self.assertEqual(reminders.run_operational_incident_alerts(), 7)
            with mock.patch.dict("os.environ", {quiet_hours.ENV_NAME: "00:00-23:59"}):
                self.assertEqual(reminders.run_operational_incident_alerts(), 0)
                self.assertEqual(reminders.run_worker_offline_reminders(), 0)
            self.assertEqual(send.call_count, 1)

    def test_both_workers_pause_polling_and_heartbeats(self):
        material = (ROOT / "material_worker.py").read_text(encoding="utf-8")
        ai = (ROOT / "ai_question_worker.py").read_text(encoding="utf-8")
        for source in (material, ai):
            self.assertIn("quiet_hours.in_quiet_hours(default=quiet_hours.DEFAULT_WORKER_QUIET_HOURS)", source)
        # The AI heartbeat thread must not keep Render awake overnight either.
        self.assertIn("continue\n            self._pulse_once()", ai)

    def test_github_schedules_skip_the_quiet_window(self):
        for name, cron in (
            ("production-smoke.yml", "17 22,23,0-16 * * *"),
            ("material-fallback-worker.yml", "7,37 22,23,0-16 * * *"),
        ):
            text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            self.assertIn(f'cron: "{cron}"', text)
        alerts = (ROOT / ".github" / "workflows" / "worker-offline-alerts.yml").read_text(encoding="utf-8")
        self.assertIn('TEACHER_QUIET_HOURS: "01:00-06:00"', alerts)


if __name__ == "__main__":
    unittest.main()
