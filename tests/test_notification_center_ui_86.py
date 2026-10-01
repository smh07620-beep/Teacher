import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NotificationCenterUi86Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = ROOT.joinpath("static", "notification-center-71.js").read_text(encoding="utf-8")
        cls.dashboard = ROOT.joinpath("teacher_app", "command_center", "dashboard_service.py").read_text(encoding="utf-8")
        cls.events = ROOT.joinpath("teacher_app", "notifications", "events.py").read_text(encoding="utf-8")

    def test_ui_persists_read_state_without_mutating_workflow_domains(self):
        for token in (
            "/api/notification-states",
            "notification-mark-all-read-71",
            "data-notification-read",
            "全部標示已讀",
            "標示未讀",
            "只保存你的已讀狀態",
            "未讀",
        ):
            self.assertIn(token, self.js)

    def test_actionable_event_keys_refresh_on_server_source_changes(self):
        self.assertIn("/api/training-command-center/notifications", self.js)
        self.assertIn("row.key", self.js)
        self.assertIn("announcementKey(item)", self.js)
        self.assertIn("def _stable_key", self.events)
        for token in (
            'item.get("persona")',
            'item.get("courseId")',
            'status',
            'due_at',
        ):
            self.assertIn(token, self.events)

        for token in (
            '"remediationRecordId"',
            '"assignmentId"',
            '"retrainingVersionKeys"',
        ):
            self.assertIn(token, self.dashboard)

    def test_browser_does_not_rebuild_actionable_event_identity(self):
        self.assertNotIn("notificationKey('pgy'", self.js)
        self.assertNotIn("notificationKey('course'", self.js)
        self.assertNotIn("notificationKey('remediation'", self.js)
        self.assertNotIn("notificationKey('exam'", self.js)
        self.assertNotIn("stableHash([...retrainingVersions]", self.js)


if __name__ == "__main__":
    unittest.main()
