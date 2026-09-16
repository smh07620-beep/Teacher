from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FinalConvergenceFacadeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.facade = (ROOT / "static" / "admin-compat-facade.js").read_text(encoding="utf-8")
        cls.wizard = (ROOT / "static" / "course-wizard-681.js").read_text(encoding="utf-8")
        cls.frontend = (ROOT / "pgy_frontend.py").read_text(encoding="utf-8")
        cls.architecture = (ROOT / "ARCHITECTURE_FINAL_CONVERGENCE.md").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github" / "workflows" / "phase3-pgy-checks.yml").read_text(encoding="utf-8")

    def test_legacy_course_wizard_globals_delegate_to_canonical_owner(self):
        self.assertIn("window.adminCreateCourseBundle=function()", self.facade)
        self.assertIn("callOwner('courseWizard681Create'", self.facade)
        self.assertIn("window.resetCourseWizardForm=function()", self.facade)
        self.assertIn("callOwner('courseWizard681Reset'", self.facade)
        self.assertIn("window.courseWizard681Create=create", self.wizard)
        self.assertIn("window.courseWizard681Reset=reset", self.wizard)

    def test_current_system_html_entrypoints_are_rewritten_to_canonical_wizard(self):
        self.assertIn(
            "html.replace('onclick=\"adminCreateCourseBundle()\"', 'onclick=\"courseWizard681Create()\"')",
            self.frontend,
        )
        self.assertIn(
            "html.replace('onclick=\"resetCourseWizardForm(true)\"', 'onclick=\"courseWizard681Reset()\"')",
            self.frontend,
        )

    def test_facade_contains_no_business_or_authorization_logic(self):
        for forbidden in (
            "fetch(",
            "XMLHttpRequest",
            "getAdminKey",
            "X-Admin-Key",
            "professional_title",
            "responsibility_tags",
            "/api/",
            "sessionStorage",
            "localStorage",
        ):
            self.assertNotIn(forbidden, self.facade)

    def test_facade_loads_last_among_injected_admin_assets(self):
        facade_marker = '<script defer src="/admin-compat-facade.js?v=7300"></script>'
        learner_marker = '<script defer src="/learner-result-chart.js?v=7123"></script>'
        self.assertIn(facade_marker, self.frontend)
        self.assertIn(learner_marker, self.frontend)
        self.assertLess(self.frontend.index(learner_marker), self.frontend.index(facade_marker))
        self.assertIn("node --check static/admin-compat-facade.js", self.workflow)

    def test_ownership_freeze_declares_system_admin_legacy_only(self):
        self.assertIn("`static/system-admin.js` is a legacy compatibility bundle", self.architecture)
        self.assertIn("`static/course-wizard-681.js` is the canonical Course Wizard UI/state owner", self.architecture)
        self.assertIn("must not receive new product logic", self.architecture)
        self.assertIn("professional_title", self.architecture)
        self.assertIn("responsibility_tags", self.architecture)


if __name__ == "__main__":
    unittest.main()
