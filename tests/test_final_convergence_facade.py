from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FinalConvergenceFacadeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wizard = (ROOT / "static" / "course-wizard-681.js").read_text(encoding="utf-8")
        cls.system = (ROOT / "static" / "system.html").read_text(encoding="utf-8")
        cls.frontend = (ROOT / "pgy_frontend.py").read_text(encoding="utf-8")
        cls.architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github" / "workflows" / "phase3-pgy-checks.yml").read_text(encoding="utf-8")

    def test_course_wizard_entrypoints_are_canonical(self):
        self.assertIn("window.courseWizard681Create=create", self.wizard)
        self.assertIn("window.courseWizard681Reset=reset", self.wizard)
        self.assertIn('onclick="courseWizard681Create()"', self.system)
        self.assertIn('onclick="courseWizard681Reset()"', self.system)

    def test_runtime_no_longer_rewrites_legacy_course_wizard_entrypoints(self):
        self.assertNotIn("adminCreateCourseBundle", self.frontend)
        self.assertNotIn("resetCourseWizardForm", self.frontend)

    def test_compatibility_facade_is_physically_removed(self):
        self.assertFalse((ROOT / "static" / "admin-compat-facade.js").exists())

    def test_release_workflow_checks_all_remaining_javascript(self):
        self.assertIn("find static -type f -name '*.js'", self.workflow)
        self.assertIn("node --check", self.workflow)

    def test_ownership_freeze_declares_system_admin_legacy_only(self):
        self.assertIn("`static/system-admin.js` is a legacy compatibility bundle", self.architecture)
        self.assertIn("`static/course-wizard-681.js` is the canonical Course Wizard UI/state owner", self.architecture)
        self.assertIn("must not receive new product logic", self.architecture)
        self.assertIn("professional_title", self.architecture)
        self.assertIn("responsibility_tags", self.architecture)


if __name__ == "__main__":
    unittest.main()
