import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class PortalInformationArchitecture73Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = ROOT.joinpath('static', 'index.html').read_text(encoding='utf-8')
        cls.internal = ROOT.joinpath('static', 'area-internal.html').read_text(encoding='utf-8')
        cls.navigation = ROOT.joinpath('static', 'portal-navigation-73.js').read_text(encoding='utf-8')
        cls.frontend = ROOT.joinpath('pgy_frontend.py').read_text(encoding='utf-8')
        cls.workflow = ROOT.joinpath('.github', 'workflows', 'phase3-pgy-checks.yml').read_text(encoding='utf-8')

    def test_home_is_task_first_dashboard_not_duplicate_management_surface(self):
        for marker in (
            '今天要做什麼？',
            '進行中課程',
            '待完成考核',
            '學習進度',
            '我的學習區域',
            'phase3-lower-focused',
        ):
            self.assertIn(marker, self.index)
        self.assertNotIn('class="v575-manage-direct"', self.index)
        self.assertNotIn('v56-panel v56-reminder', self.index)
        self.assertIn('/phase3.css?v=7300', self.index)

    def test_internal_area_is_selection_surface_only(self):
        self.assertIn('一個組別，一個學習中心', self.internal)
        self.assertIn('院內課程', self.internal)
        self.assertNotIn('class="v575-manage-direct"', self.internal)
        self.assertNotIn('>PGY 專區<', self.internal)
        self.assertIn('from=area', self.internal)

    def test_navigation_convergence_is_one_shot_and_has_no_observer(self):
        self.assertIn("if(document.readyState==='loading')", self.navigation)
        self.assertIn("normalizePublicPortal", self.navigation)
        self.assertIn("normalizeSystem", self.navigation)
        self.assertIn("data-portal73-area-link", self.navigation)
        self.assertNotIn('new MutationObserver', self.navigation)
        self.assertNotIn("setInterval", self.navigation)

    def test_navigation_asset_is_composed_and_syntax_checked(self):
        self.assertIn('/portal-navigation-73.js?v=7300', self.frontend)
        self.assertIn('node --check static/portal-navigation-73.js', self.workflow)


if __name__ == '__main__':
    unittest.main()
