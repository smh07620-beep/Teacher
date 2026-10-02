import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.maintenance.notification_preference_migration import notification_email_preferences_106
from teacher_app.notifications import preferences


ROOT = Path(__file__).resolve().parents[1]


class NotificationPreference0106Tests(unittest.TestCase):
    def test_migration_adds_only_preference_table_with_default_on_categories(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        notification_email_preferences_106(conn, "sqlite")
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(notification_email_preferences)")}
        self.assertEqual(columns["username"][5], 1)
        for name in ("email_course_due", "email_exam_due", "email_retraining", "email_teacher_review"):
            self.assertIn(name, columns)
            self.assertEqual(str(columns[name][4]).strip("'\""), "1")

    def test_ordinary_email_categories_respect_preferences_but_critical_failure_cannot_be_disabled(self):
        rows = [
            {"kind": "course", "key": "c"},
            {"kind": "exam", "key": "e"},
            {"kind": "retraining", "key": "r"},
            {"kind": "review", "key": "v"},
            {"kind": "material_failure", "key": "f"},
            {"kind": "worker_offline", "key": "w"},
        ]
        stored = {
            "emailCategories": {
                "courseDue": False,
                "examDue": False,
                "retraining": False,
                "teacherReview": False,
            },
            "protectedCategories": ["materialFailure", "workerOffline"],
        }
        with patch.object(preferences, "get_preferences", return_value=stored):
            filtered = preferences.filter_email_events(rows, {"username": "u1"}, general_enabled=True)
            self.assertEqual([row["kind"] for row in filtered], ["material_failure", "worker_offline"])
            filtered_master_off = preferences.filter_email_events(rows, {"username": "u1"}, general_enabled=False)
            self.assertEqual([row["kind"] for row in filtered_master_off], ["material_failure", "worker_offline"])

    def test_preference_api_and_ui_are_session_scoped_and_do_not_hide_in_app_tasks(self):
        routes = ROOT.joinpath("teacher_app", "command_center", "notification_routes.py").read_text(encoding="utf-8")
        reminders = ROOT.joinpath("teacher_app", "notifications", "reminders.py").read_text(encoding="utf-8")
        ui = ROOT.joinpath("static", "notification-center-71.js").read_text(encoding="utf-8")
        service = ROOT.joinpath("teacher_app", "notifications", "preferences.py").read_text(encoding="utf-8")

        self.assertIn("/api/notification-preferences", routes)
        self.assertIn("_current_user(owner)", routes)
        self.assertNotIn('data.get("username")', routes)
        self.assertIn("preferences.filter_email_events", reminders)
        self.assertNotIn("assignment_service", reminders)
        self.assertNotIn("progress_service", reminders)
        self.assertIn("只控制 Email；站內待辦仍會完整顯示", ui)
        self.assertIn("教材處理失敗（必要通知）", ui)
        self.assertIn("Worker 離線（必要通知）", ui)
        self.assertIn("查看 Worker 狀態", ui)
        self.assertIn("notificationContext='system'", ui)
        self.assertIn("protectedCategories", service)
        self.assertIn('CRITICAL_KINDS = {"material_failure", "worker_offline"}', service)
        self.assertIn('["materialFailure", "workerOffline"]', service)

    def test_payload_cannot_select_another_account_or_disable_protected_kind(self):
        source = ROOT.joinpath("teacher_app", "notifications", "preferences.py").read_text(encoding="utf-8")
        self.assertIn('username = str((user or {}).get("username")', source)
        self.assertNotIn('payload.get("username")', source)
        self.assertNotIn('"materialFailure": True', source)
        self.assertIn("if kind in CRITICAL_KINDS", source)


if __name__ == "__main__":
    unittest.main()
