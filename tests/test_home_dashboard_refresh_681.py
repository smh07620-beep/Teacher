import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class HomeDashboardRefresh681Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath("static", "index.html").read_text(encoding="utf-8")
        cls.css = ROOT.joinpath("static", "portal.css").read_text(encoding="utf-8")
        cls.runtime = ROOT.joinpath("static", "portal-v56.js").read_text(encoding="utf-8")
        cls.todo = ROOT.joinpath("static", "learner-todo-convergence-1025.js").read_text(encoding="utf-8")

    def test_home_header_is_intentionally_minimal(self):
        header = self.html[self.html.index('<header class="v56-header">'):self.html.index('</header>')]
        self.assertIn('aria-current="page">首頁</a>', header)
        self.assertNotIn('>課程</a>', header)
        self.assertNotIn('>考核</a>', header)
        self.assertNotIn('data-v56-search', header)
        self.assertIn('v571-notice-trigger', header)
        self.assertIn('v561-profile-trigger', header)

    def test_home_has_three_summary_cards_and_contextual_announcement_strip(self):
        self.assertIn('id="v561-course-count"', self.html)
        self.assertIn('id="v561-progress-percent"', self.html)
        self.assertIn('id="v681-home-todo-count"', self.html)
        self.assertEqual(self.html.count('class="phase3-stat '), 3)
        self.assertIn('id="v681-announcement-strip"', self.html)
        self.assertIn('id="v681-announcement-open"', self.html)
        self.assertIn("strip.hidden=!rows.length", self.runtime)

    def test_progress_card_is_real_area_aware_training_progress_entry(self):
        self.assertIn('id="v561-progress-open" data-home-progress-link', self.html)
        self.assertIn('學習進度', self.html)
        self.assertIn('module=progress&amp;from=home', self.html)
        self.assertGreaterEqual(self.html.count('data-home-progress-link'), 2)
        self.assertIn("progressLinks=$$('[data-home-progress-link]')", self.runtime)
        self.assertIn("module:'progress'", self.runtime)
        self.assertIn("progressGroup=next==='pgy'?'grpNew':'grpBio'", self.runtime)
        self.assertIn("function setupProgressEntry()", self.runtime)
        self.assertIn("/login?next=${encodeURIComponent(href)}", self.runtime)

    def test_learning_centres_keep_all_six_canonical_links(self):
        for group in ("grpBio", "grpMicro", "grpSero", "grpBB", "grpBact", "grpHema"):
            self.assertIn(f'group={group}&amp;module=materials&amp;from=home', self.html)
        self.assertEqual(self.html.count('進入學習中心 <i>→</i>'), 6)
        self.assertIn('data-phase3-area="internal"', self.html)
        self.assertIn('data-phase3-area="pgy"', self.html)

    def test_home_progress_and_todo_use_canonical_command_center_sources(self):
        self.assertIn("/api/training-command-center/progress", self.runtime)
        self.assertNotIn("/api/dashboard/me", self.runtime)
        self.assertNotIn("renderPendingExams(", self.runtime)
        self.assertNotIn("v681-home-todo-count", self.runtime)
        self.assertNotIn("v561-progress-percent", self.runtime)
        self.assertIn("/api/training-command-center", self.todo)
        self.assertIn("v681-home-todo-count", self.todo)
        self.assertIn("v681-home-materials-pending", self.todo)
        self.assertIn("v681-home-exams-pending", self.todo)
        self.assertNotIn("setTimeout(load,800)", self.todo)

    def test_visual_refresh_is_home_scoped(self):
        self.assertIn('home-dashboard-page', self.html)
        self.assertIn('.home-dashboard-page .v56-header', self.css)
        self.assertIn('.phase3-home .phase3-home-hero-681', self.css)
        self.assertIn('.phase3-home .phase3-groups', self.css)
        self.assertIn('.phase3-announcement-strip[hidden]', self.css)


if __name__ == '__main__':
    unittest.main()
