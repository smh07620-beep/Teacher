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

    def test_recovered_operational_incidents_are_informational_not_pending_work(self):
        self.assertIn("!['announcement','operational_recovery'].includes(row.kind)", self.js)
        self.assertIn("item.kind==='operational_recovery'", self.js)
        self.assertIn("查看目前狀態", self.js)

    def test_system_admin_notifications_use_system_workspace_not_hidden_learner_dom(self):
        for token in (
            "function isSystemContext()",
            "admin-workspace-content",
            "section.dataset.notificationContext='system'",
            "section.dataset.productSection='needs-action'",
            "item.kind==='worker_offline'",
            "查看 Worker 狀態",
            "Worker 離線（必要通知）",
        ):
            self.assertIn(token, self.js)
        self.assertIn("isSystemContext()?Promise.resolve([])", self.js)


    def test_learner_notification_surface_requests_learner_persona_and_hides_incidents(self):
        self.assertIn("function isLearnerContext()", self.js)
        self.assertIn("/api/training-command-center/notifications?persona=learner", self.js)
        self.assertIn('persona_mode != "learner"', self.events)
        self.assertIn('incident_events = [] if persona_mode == "learner"', self.events)

    def test_system_notification_center_escapes_workspace_clipping_when_expanded(self):
        admin_css = ROOT.joinpath("static", "admin.css").read_text(encoding="utf-8")
        for token in (
            "function openSystemOverlay(section)",
            "function closeSystemOverlay(section)",
            "notification-center-backdrop-71",
            "notification-center-modal-open",
            "document.body.appendChild(section)",
            "event.key!=='Escape'",
        ):
            self.assertIn(token, self.js)
        for token in (
            "#notification-center-71.notification-center-modal-open",
            ".notification-center-backdrop-71",
            "body.notification-center-open-71",
            "position: fixed !important",
        ):
            self.assertIn(token, admin_css)

    def test_browser_does_not_rebuild_actionable_event_identity(self):
        self.assertNotIn("notificationKey('pgy'", self.js)
        self.assertNotIn("notificationKey('course'", self.js)
        self.assertNotIn("notificationKey('remediation'", self.js)
        self.assertNotIn("notificationKey('exam'", self.js)
        self.assertNotIn("stableHash([...retrainingVersions]", self.js)


if __name__ == "__main__":
    unittest.main()
