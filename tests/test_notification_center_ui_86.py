import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NotificationCenterUi86Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = ROOT.joinpath("static", "notification-center-71.js").read_text(encoding="utf-8")
        cls.dashboard = ROOT.joinpath("teacher_app", "command_center", "dashboard_service.py").read_text(encoding="utf-8")

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

    def test_event_keys_refresh_for_changed_source_events(self):
        for token in (
            "notificationKey('pgy'",
            "notificationKey('course'",
            "notificationKey('remediation'",
            "notificationKey('exam'",
            "notificationKey('announcement'",
            "stableHash([...retrainingVersions].sort().join('|'))",
        ):
            self.assertIn(token, self.js)

        for token in (
            '"remediationRecordId"',
            '"assignmentId"',
            '"retrainingVersionKeys"',
        ):
            self.assertIn(token, self.dashboard)


if __name__ == "__main__":
    unittest.main()
