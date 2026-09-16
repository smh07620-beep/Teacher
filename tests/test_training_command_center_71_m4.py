import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NotificationCenter71Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = ROOT.joinpath("static", "notification-center-71.js").read_text(encoding="utf-8")
        cls.frontend = ROOT.joinpath("pgy_frontend.py").read_text(encoding="utf-8")
        cls.workflow = ROOT.joinpath(".github", "workflows", "phase3-pgy-checks.yml").read_text(encoding="utf-8")
        cls.coverage = ROOT.joinpath("RC_FEATURE_UI_COVERAGE_MATRIX.md").read_text(encoding="utf-8")

    def test_m4_is_normal_read_only_notification_surface(self):
        self.assertIn("🔔 通知中心", self.ui)
        self.assertIn("唯讀聚合層", self.ui)
        for mutation in ("method: 'POST'", 'method: "POST"', "method: 'PATCH'", "method: 'DELETE'"):
            self.assertNotIn(mutation, self.ui)

    def test_m4_reuses_existing_canonical_read_apis(self):
        for contract in (
            "/api/auth/me",
            "/api/training-command-center",
            "/api/dashboard/me?",
            "/api/announcements?limit=5",
        ):
            self.assertIn(contract, self.ui)
        self.assertNotIn("/api/training-command-center/notifications", self.ui)

    def test_m4_preserves_action_ownership(self):
        self.assertIn("switchLearningModule", self.ui)
        self.assertIn("module: 'exam'", self.ui)
        self.assertNotIn("teacher-sign", self.ui)
        self.assertNotIn("countersign", self.ui)
        self.assertNotIn("finalize", self.ui)
        self.assertNotIn("/api/announcements/admin", self.ui)

    def test_m4_asset_loads_after_m3_and_is_syntax_checked(self):
        self.assertIn('/notification-center-71.js?v=7103', self.frontend)
        self.assertLess(
            self.frontend.index('/learning-analytics-71.js?v=7102'),
            self.frontend.index('/notification-center-71.js?v=7103'),
        )
        self.assertIn("node --check static/notification-center-71.js", self.workflow)

    def test_rc_matrix_records_m4(self):
        self.assertIn("Notification Center (7.1 M4)", self.coverage)
        self.assertIn("static/notification-center-71.js", self.coverage)
        self.assertIn("/api/dashboard/me", self.coverage)
        self.assertIn("no new mutation API", self.coverage)


if __name__ == "__main__":
    unittest.main()
