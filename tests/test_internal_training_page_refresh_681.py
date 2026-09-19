from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InternalTrainingPageRefresh681Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath("static", "area-internal.html").read_text(encoding="utf-8")
        cls.css = ROOT.joinpath("static", "portal.css").read_text(encoding="utf-8")

    def test_internal_page_has_no_visible_assessment_navigation_or_copy(self):
        self.assertNotIn('href="/#pending-exams"', self.html)
        self.assertNotIn('>考核<', self.html)
        self.assertNotIn('進行考核', self.html)
        self.assertNotIn('教材、考核', self.html)

    def test_approved_internal_hero_structure_is_present(self):
        for marker in (
            'v681-internal-hero',
            'v681-internal-features',
            '快速開始',
            '多元學習資源',
            '依專業組別瀏覽',
            '隨時線上學習',
            '圖譜與 SOP',
        ):
            self.assertIn(marker, self.html)

    def test_existing_six_group_routes_are_preserved(self):
        for group in ('grpBio', 'grpMicro', 'grpSero', 'grpBB', 'grpBact', 'grpHema'):
            self.assertIn(f'group={group}&amp;module=materials', self.html)
        self.assertEqual(self.html.count('進入學習中心 →'), 6)

    def test_internal_refresh_is_page_scoped_and_mobile_friendly(self):
        self.assertIn('.internal-training-page', self.css)
        self.assertIn('.v681-internal-hero', self.css)
        self.assertIn('grid-template-columns:repeat(2,1fr)', self.css)
        self.assertIn('.internal-training-page .v56-header.menu-open .v56-nav', self.css)


if __name__ == "__main__":
    unittest.main()
