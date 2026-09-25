import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NotificationCenter71Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = ROOT.joinpath("static", "notification-center-71.js").read_text(encoding="utf-8")
        cls.frontend = ROOT.joinpath("teacher_app", "frontend", "assets.py").read_text(encoding="utf-8")
        cls.workflow = ROOT.joinpath(".github", "workflows", "phase3-pgy-checks.yml").read_text(encoding="utf-8")
        cls.coverage = ROOT.joinpath("RC_FEATURE_UI_COVERAGE_MATRIX.md").read_text(encoding="utf-8")

    def test_m4_only_mutates_personal_read_markers(self):
        self.assertIn("🔔 通知中心", self.ui)
        self.assertIn("只保存你的已讀狀態", self.ui)
        self.assertIn("/api/notification-states", self.ui)
        self.assertIn("method: 'PATCH'", self.ui)
        for mutation in ("method: 'POST'", 'method: "POST"', "method: 'DELETE'"):
            self.assertNotIn(mutation, self.ui)

    def test_m4_reuses_existing_canonical_read_apis(self):
        for contract in ("/api/auth/me", "/api/training-command-center", "/api/dashboard/me?", "/api/announcements?limit=5"):
            self.assertIn(contract, self.ui)
        self.assertNotIn("/api/training-command-center/notifications", self.ui)

    def test_m4_preserves_action_ownership(self):
        self.assertIn("switchLearningModule", self.ui)
        self.assertIn("module: 'exam'", self.ui)
        self.assertNotIn("teacher-sign", self.ui)
        self.assertNotIn("countersign", self.ui)
        self.assertNotIn("finalize", self.ui)
        self.assertNotIn("/api/announcements/admin", self.ui)

    def test_m4_sits_after_course_grid_and_asset_loads_after_m3(self):
        self.assertIn("document.getElementById('course-overview-grid')", self.ui)
        self.assertIn('/notification-center-71.js', self.frontend)
        self.assertLess(self.frontend.index('/learning-analytics-71.js'), self.frontend.index('/notification-center-71.js'))
        self.assertIn("find static -type f -name '*.js'", self.workflow)

    def test_rc_matrix_records_m4(self):
        self.assertIn("Notification Center + durable read state (7.1 M4 / 8.6)", self.coverage)
        self.assertIn("static/notification-center-71.js", self.coverage)
        self.assertIn("/api/dashboard/me", self.coverage)
        self.assertIn("GET/PATCH /api/notification-states", self.coverage)
        self.assertIn("read markers", self.coverage)


if __name__ == "__main__":
    unittest.main()
