import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AccessibilityRegressionGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = ROOT.joinpath("tests", "playwright", "accessibility-regression.spec.js").read_text(encoding="utf-8")
        cls.workflow = ROOT.joinpath(".github", "workflows", "playwright-ui-checks.yml").read_text(encoding="utf-8")
        cls.home = ROOT.joinpath("static", "index.html").read_text(encoding="utf-8")
        cls.internal = ROOT.joinpath("static", "area-internal.html").read_text(encoding="utf-8")
        cls.pgy = ROOT.joinpath("static", "area-pgy.html").read_text(encoding="utf-8")
        cls.system = ROOT.joinpath("static", "system.html").read_text(encoding="utf-8")

    def test_ci_runs_accessibility_browser_gate(self):
        self.assertIn("Run accessibility browser regressions", self.workflow)
        self.assertIn("tests/playwright/accessibility-regression.spec.js", self.workflow)
        self.assertIn("--workers=1", self.workflow)

    def test_browser_gate_covers_core_regressions(self):
        for token in (
            "missing html[lang]",
            "duplicate #",
            "missing alt attribute",
            "positive tabindex",
            "has no accessible name",
            "aria-hidden:",
            "horizontal overflow",
            "keyboard focus remains visible",
            "profile dialog is keyboard-operable",
        ):
            self.assertIn(token, self.spec)
        for path in ("/", "/internal", "/pgy", "/system?area=internal&group=grpBio&module=materials"):
            self.assertIn(path, self.spec)

    def test_learner_dialogs_are_programmatically_named(self):
        for html in (self.home, self.internal, self.pgy):
            self.assertIn('id="v571-announcement-dialog" class="v561-profile-dialog v571-announcement-dialog" aria-label="最新公告"', html)
            self.assertIn('id="v561-profile-dialog" class="v561-profile-dialog" aria-label="個人學習資料"', html)

    def test_pgy_navigation_has_landmark_and_current_page(self):
        self.assertIn('class="v56-bottom-nav" aria-label="行動版 PGY 導覽"', self.pgy)
        self.assertIn('class="active" href="/pgy" aria-current="page"', self.pgy)
        self.assertIn('class="v56-brand" href="/" aria-label="醫學檢驗教學平台首頁"', self.pgy)

    def test_resource_search_input_has_programmatic_label(self):
        self.assertIn('label for="resource-search-input"', self.system)
        self.assertIn('id="resource-search-input"', self.system)


if __name__ == "__main__":
    unittest.main()
