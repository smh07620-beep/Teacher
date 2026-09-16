from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Phase3LAdminResultsWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = (ROOT / "static" / "admin-workspace.js").read_text(encoding="utf-8")
        cls.results = (ROOT / "static" / "admin-results-workspace.js").read_text(encoding="utf-8")
        cls.frontend = (ROOT / "pgy_frontend.py").read_text(encoding="utf-8")

    def test_workspace_router_no_longer_delegates_teacher_results_to_legacy_switch(self):
        self.assertNotIn("legacySwitchWorkspace", self.router)
        self.assertIn("window.__teacherAdminResultsWorkspace", self.router)
        self.assertIn("modeRouter.switchWorkspace", self.router)
        self.assertIn("requested, workspace:name, force, switchSection", self.router)

    def test_results_mode_owns_scoring_filter_and_teacher_mode(self):
        self.assertIn("teacherMode: 'scoring'", self.results)
        self.assertIn("resultMode: 'results'", self.results)
        self.assertIn("record?.reviewStatus === 'pending'", self.results)
        self.assertIn("answer?.questionType === 'essay'", self.results)
        self.assertIn("window.fetchAdminRecords = filteredFetchAdminRecords", self.results)
        self.assertIn("window.switchTeacherMode = switchTeacherMode", self.results)
        self.assertIn("window.__teacherAdminResultsWorkspace", self.results)

    def test_scoring_mode_hides_analytics_and_preserves_empty_state(self):
        self.assertIn("admin-results-analytics", self.results)
        self.assertIn("目前沒有待人工評分的考核。", self.results)
        self.assertIn("🎯 待人工評分", self.results)
        self.assertIn("📊 歷次考核成績", self.results)

    def test_router_and_mode_state_load_before_rbac_wrappers(self):
        self.assertIn('workspace_marker = \'<script defer src="/admin-workspace.js?v=7110"></script>\'', self.frontend)
        self.assertIn('results_mode_marker = \'<script defer src="/admin-results-workspace.js?v=7111"></script>\'', self.frontend)
        self.assertIn("replacement = legacy_admin_marker + \"\\n\" + workspace_marker", self.frontend)
        self.assertIn("replacement += \"\\n\" + results_mode_marker", self.frontend)

    def test_results_mode_does_not_introduce_authorization_logic(self):
        self.assertNotIn("professionalTitle", self.results)
        self.assertNotIn("responsibilityTags", self.results)
        self.assertNotIn("X-Admin-Key", self.results)
        self.assertNotIn("/api/", self.results)


if __name__ == "__main__":
    unittest.main()
