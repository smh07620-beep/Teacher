import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.notifications import reminders


ROOT = Path(__file__).parents[1]


class WorkerOfflineEmailSchedule20261002Tests(unittest.TestCase):
    def test_sender_targets_only_system_admin_and_keeps_critical_alert_when_general_email_is_off(self):
        users = [
            {
                "username": "student1",
                "display_name": "學員",
                "email": "student@example.test",
                "active": True,
                "role": "student",
                "roles": ["student"],
                "email_notifications": False,
            },
            {
                "username": "sys1",
                "display_name": "系統管理",
                "email": "sys@example.test",
                "active": True,
                "role": "system_admin",
                "roles": ["system_admin"],
                "email_notifications": False,
            },
        ]
        event = {
            "key": "notify:worker_offline:abc",
            "kind": "worker_offline",
            "title": "教材 Worker 已離線",
            "badge": "Worker 離線",
            "detail": "worker-a 已超過 10 分鐘未回報心跳。",
            "dueAt": "",
            "channels": ["in_app", "email"],
            "emailPolicy": "once",
        }

        def project(user, **_kwargs):
            return {"items": [event] if user["username"] == "sys1" else []}

        with patch.object(reminders.auth_repository, "list_users", return_value=users), \
             patch.object(reminders.events, "build_events", side_effect=project) as build, \
             patch.object(reminders.preferences, "filter_email_events", side_effect=lambda rows, *_args, **_kwargs: list(rows)) as filtering, \
             patch.object(reminders, "_claim", return_value=True), \
             patch.object(reminders, "_send", return_value=True) as send:
            sent = reminders.run_worker_offline_reminders()

        self.assertEqual(sent, 1)
        self.assertEqual(build.call_count, 1)
        filtering.assert_called_once()
        self.assertFalse(filtering.call_args.kwargs["general_enabled"])
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], "sys@example.test")
        self.assertIn("Worker 離線提醒", send.call_args.args[1])

    def test_failed_worker_alert_email_releases_claim_for_retry(self):
        user = {
            "username": "sys1",
            "display_name": "系統管理",
            "email": "sys@example.test",
            "active": True,
            "role": "system_admin",
            "roles": ["system_admin"],
        }
        event = {
            "key": "notify:worker_offline:abc",
            "kind": "worker_offline",
            "title": "教材 Worker 已離線",
            "badge": "Worker 離線",
            "detail": "worker-a 已離線。",
            "dueAt": "",
            "channels": ["in_app", "email"],
            "emailPolicy": "once",
        }
        with patch.object(reminders.auth_repository, "list_users", return_value=[user]), \
             patch.object(reminders.events, "build_events", return_value={"items": [event]}), \
             patch.object(reminders.preferences, "filter_email_events", side_effect=lambda rows, *_args, **_kwargs: list(rows)), \
             patch.object(reminders, "_claim", return_value=True), \
             patch.object(reminders, "_send", return_value=False), \
             patch.object(reminders, "_release_claim") as release:
            sent = reminders.run_worker_offline_reminders()
        self.assertEqual(sent, 0)
        release.assert_called_once_with("sys1", event["key"])

    def test_workflow_is_ten_minute_critical_lane_and_daily_reminders_stay_daily(self):
        critical = ROOT.joinpath(".github", "workflows", "worker-offline-alerts.yml").read_text(encoding="utf-8")
        daily = ROOT.joinpath(".github", "workflows", "email-reminders.yml").read_text(encoding="utf-8")
        script = ROOT.joinpath("scripts", "send_worker_offline_alerts.py").read_text(encoding="utf-8")
        self.assertIn('cron: "*/10 * * * *"', critical)
        self.assertIn('MATERIAL_WORKER_OFFLINE_ALERT_SECONDS: "600"', critical)
        self.assertIn("send_worker_offline_alerts.py", critical)
        self.assertIn("run_worker_offline_reminders", script)
        self.assertIn('cron: "15 1 * * *"', daily)
        self.assertNotIn('*/10', daily)


if __name__ == "__main__":
    unittest.main()
