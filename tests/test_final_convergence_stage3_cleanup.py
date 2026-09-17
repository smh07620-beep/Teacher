from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FinalConvergenceStage3CleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = (ROOT / "static" / "admin-runtime-shared.js").read_text(encoding="utf-8")
        cls.docx = (ROOT / "static" / "admin-results-docx-fallback.js").read_text(encoding="utf-8")
        cls.wizard = (ROOT / "static" / "course-wizard-681.js").read_text(encoding="utf-8")
        cls.facade = (ROOT / "static" / "admin-compat-facade.js").read_text(encoding="utf-8")
        cls.frontend = (ROOT / "pgy_frontend.py").read_text(encoding="utf-8")

    def test_legacy_admin_bundle_is_physically_removed(self):
        self.assertFalse((ROOT / "static" / "system-admin.js").exists())
        self.assertIn("legacy_admin_marker", self.frontend)
        self.assertIn("admin-runtime-shared.js?v=7400", self.frontend)
        self.assertIn("html.replace(legacy_admin_marker, runtime_admin_marker, 1)", self.frontend)

    def test_canonical_wizard_and_facade_contract_remain(self):
        self.assertIn("window.courseWizard681Create=create", self.wizard)
        self.assertIn("window.courseWizard681Reset=reset", self.wizard)
        self.assertIn("callOwner('courseWizard681Create'", self.facade)
        self.assertIn("callOwner('courseWizard681Reset'", self.facade)

    def test_docx_local_fallback_ownership_moved_out_of_legacy_bundle(self):
        self.assertIn("let cachedTemplateBuffer=null", self.docx)
        self.assertIn("let pendingExportRecordIndex=null", self.docx)
        self.assertIn("docx-template-input", self.docx)
        self.assertIn("window.exportRecordToWord", self.docx)

    def test_admin_key_is_shared_session_rbac_compatibility_only(self):
        self.assertIn("async function getAdminKey()", self.shared)
        self.assertIn("return 'rbac-session';", self.shared)
        self.assertIn("compatibility header seam", self.shared)
        self.assertNotIn("prompt(", self.shared)
        self.assertNotIn("sessionStorage", self.shared)


if __name__ == "__main__":
    unittest.main()
