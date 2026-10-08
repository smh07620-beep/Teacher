import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AnalyticsCollapseTests(unittest.TestCase):
    def setUp(self):
        self.js = (ROOT / "static/teacher-learners-p2.js").read_text(encoding="utf-8")

    def test_summary_is_one_line_and_tiles_are_gone(self):
        self.assertIn('id="teacher-learners-summary-p2"', self.js)
        self.assertIn('id="teacher-analytics-line-p2"', self.js)
        self.assertNotIn("grid grid-cols-2 sm:grid-cols-4 gap-2 text-center", self.js)

    def test_analytics_detail_is_collapsed_by_default_and_toggles(self):
        self.assertIn('id="teacher-teaching-analytics-p2" class="hidden', self.js)
        for marker in ("📊 展開教學分析", "📊 收合教學分析", "toggleTeachingAnalytics", "aria-expanded"):
            self.assertIn(marker, self.js)

    def test_analytics_tab_expands_the_detail(self):
        ws = (ROOT / "static/teacher-workspace-1014.js").read_text(encoding="utf-8")
        self.assertIn("TeacherLearnersP2?.openAnalytics", ws)
        self.assertIn("openAnalytics", self.js)

    def test_data_still_comes_from_scoped_server_endpoints(self):
        self.assertIn("/api/training-command-center/teacher-analytics", self.js)
        self.assertIn("/api/training-command-center/teacher-learners", self.js)


if __name__ == "__main__":
    unittest.main()
