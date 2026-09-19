from pathlib import Path
import unittest

from pgy_frontend import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class Phase3LAdminResultsWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = (ROOT / "static" / "admin-workspace.js").read_text(encoding="utf-8")
        cls.results = (ROOT / "static" / "admin-results-workspace.js").read_text(encoding="utf-8")
        cls.frontend = (ROOT / "pgy_frontend.py").read_text(encoding="utf-8")

    def test_workspace_router_no_longer_delegates_teacher_results_to_legacy_switch(self):
        self.assertNotIn("legacySwitchWorkspace", self.router)
        self.assertNotIn("window.__teacherAdminResultsWorkspace", self.router)
        self.assertNotIn("modeRouter.switchWorkspace", self.router)
        self.assertIn("registerWorkspace('teacher', switchWorkspace)", self.results)
        self.assertIn("registerWorkspace('results', switchWorkspace)", self.results)

    def test_results_mode_owns_scoring_filter_and_teacher_mode(self):
        self.assertIn("teacherMode: 'scoring'", self.results)
        self.assertIn("resultMode: 'results'", self.results)
        self.assertIn("record?.reviewStatus === 'pending'", self.results)
        self.assertIn("answer?.questionType === 'essay'", self.results)
        self.assertIn("window.fetchAdminRecords = filteredFetchAdminRecords", self.results)
        self.assertIn("window.switchTeacherMode = switchTeacherMode", self.results)
        self.assertNotIn("window.__teacherAdminResultsWorkspace", self.results)

    def test_scoring_mode_hides_analytics_and_preserves_empty_state(self):
        self.assertIn("admin-results-analytics", self.results)
        self.assertIn("目前沒有待人工評分的考核。", self.results)
        self.assertIn("🎯 教師評核｜待人工評分", self.results)
        self.assertIn("📊 歷次考核成績", self.results)

    def test_teacher_scoring_reuses_raw_records_for_activity_and_keeps_action_indexes_aligned(self):
        self.assertIn("window.renderAdminActivitySummary?.(records)", self.results)
        self.assertIn("const filtered = records.filter(isScoringRecord)", self.results)
        self.assertIn("adminRecords = filtered", self.results)
        self.assertIn("document.getElementById('admin-table-body')", self.results)

    def test_router_and_mode_state_load_before_rbac_wrappers(self):
        ordered = dict(ASSET_MANIFEST["system"]["ordered"])["/system-admin.js"]
        self.assertLess(ordered.index("/admin-workspace.js"), ordered.index("/admin-results-workspace.js"))
        self.assertNotIn("workspace_marker =", self.frontend)
        self.assertNotIn("results_mode_marker =", self.frontend)

    def test_results_mode_does_not_introduce_authorization_logic(self):
        self.assertNotIn("professionalTitle", self.results)
        self.assertNotIn("responsibilityTags", self.results)
        self.assertNotIn("X-Admin-Key", self.results)
        self.assertNotIn("/api/", self.results)


if __name__ == "__main__":
    unittest.main()
