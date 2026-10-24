"""Scheduled reminder digest must finish within its time budget and rotate users."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from teacher_app.notifications import reminders

ROOT = Path(__file__).resolve().parents[1]


def _rows(count: int) -> list[dict]:
    return [
        {"username": f"u{i:03d}", "display_name": f"U{i}", "email": f"u{i}@x.org", "active": 1}
        for i in range(count)
    ]


class EmailReminderBudgetTests(unittest.TestCase):
    def _run(self, rows, process, env):
        with mock.patch.object(reminders.auth_repository, "list_users", return_value=rows), \
             mock.patch.object(reminders, "_process_user", side_effect=process), \
             mock.patch.object(reminders, "_start_reminder_run"), \
             mock.patch.object(reminders, "_finish_reminder_run") as finish, \
             mock.patch.dict(os.environ, env):
            sent = reminders.run_due_reminders()
        return sent, finish

    def test_processes_every_eligible_user_and_skips_inactive_or_no_email(self):
        rows = _rows(30) + [
            {"username": "off", "email": "o@x.org", "active": 0},
            {"username": "nomail", "email": "", "active": 1},
        ]
        seen = []

        def process(row, **_kwargs):
            seen.append(row["username"])
            return {"sent": 1, "expected": 1, "claimed": 1, "sent_events": 1, "failed_events": 0}

        sent, finish = self._run(rows, process, {"EMAIL_REMINDER_CONCURRENCY": "4"})
        self.assertEqual(sent, 30)
        self.assertEqual(sorted(seen), [f"u{i:03d}" for i in range(30)])
        self.assertFalse(finish.call_args.kwargs["incomplete"])

    def test_stops_starting_users_after_time_budget_and_records_partial(self):
        clock = {"t": 0.0}

        def process(row, **_kwargs):
            clock["t"] += 10.0
            return {"sent": 1, "expected": 1, "claimed": 1, "sent_events": 1, "failed_events": 0}

        with mock.patch.object(reminders.time, "monotonic", side_effect=lambda: clock["t"]):
            sent, finish = self._run(
                _rows(20),
                process,
                {"EMAIL_REMINDER_CONCURRENCY": "1", "EMAIL_REMINDER_TIME_BUDGET_SECONDS": "30"},
            )
        self.assertLess(sent, 20)
        self.assertGreater(sent, 0)
        self.assertTrue(finish.call_args.kwargs["incomplete"])

    def test_order_rotates_by_day_but_is_stable_within_a_day(self):
        rows = _rows(50)
        day1 = [r["username"] for r in reminders._daily_order(rows, "2026-10-24")]
        again = [r["username"] for r in reminders._daily_order(rows, "2026-10-24")]
        day2 = [r["username"] for r in reminders._daily_order(rows, "2026-10-25")]
        self.assertEqual(day1, again)
        self.assertNotEqual(day1, day2)
        self.assertEqual(sorted(day1), sorted(day2))

    def test_workflow_timeout_exceeds_script_budget(self):
        workflow = ROOT.joinpath(".github", "workflows", "email-reminders.yml").read_text(encoding="utf-8")
        self.assertIn("timeout-minutes: 25", workflow)
        self.assertIn('EMAIL_REMINDER_TIME_BUDGET_SECONDS: "900"', workflow)


if __name__ == "__main__":
    unittest.main()
