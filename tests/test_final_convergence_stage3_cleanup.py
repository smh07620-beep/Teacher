from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FinalConvergenceStage3CleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy = (ROOT / "static" / "system-admin.js").read_text(encoding="utf-8")
        cls.wizard = (ROOT / "static" / "course-wizard-681.js").read_text(encoding="utf-8")
        cls.facade = (ROOT / "static" / "admin-compat-facade.js").read_text(encoding="utf-8")

    def test_legacy_bundle_no_longer_owns_course_wizard_runtime(self):
        for forbidden in (
            "let courseWizardBusy=false",
            "function setCourseWizardProgress(",
            "function setCourseWizardDetail(",
            "function pollWizardUploadProgress(",
            "function waitWizardMaterialJob(",
            "function uploadWizardMaterial(",
            "const WIZARD_MATERIAL_TYPE_META=",
            "let wizardMaterialTypes=",
            "let wizardMaterialTitles=",
            "function suggestWizardMaterialType(",
            "function wizardMaterialTypeOptions(",
            "function renderWizardMaterialClassifier(",
            "function applyWizardMaterialBulkType(",
            "function setCourseWizardBusy(",
            "function resetCourseWizardForm(",
            "async function adminCreateCourseBundle(",
        ):
            self.assertNotIn(forbidden, self.legacy)

    def test_canonical_wizard_and_facade_contract_remain(self):
        self.assertIn("window.courseWizard681Create=create", self.wizard)
        self.assertIn("window.courseWizard681Reset=reset", self.wizard)
        self.assertIn("callOwner('courseWizard681Create'", self.facade)
        self.assertIn("callOwner('courseWizard681Reset'", self.facade)

    def test_docx_local_fallback_state_stays_until_ownership_moves(self):
        self.assertIn("let cachedTemplateBuffer = null", self.legacy)
        self.assertIn("let pendingExportRecordIndex = null", self.legacy)
        self.assertIn("docx-template-input", self.legacy)

    def test_admin_key_remains_session_rbac_compatibility_only(self):
        self.assertIn("async function getAdminKey()", self.legacy)
        self.assertIn("return 'rbac-session';", self.legacy)
        self.assertIn("no ADMIN_KEY is prompted for or persisted", self.legacy)


if __name__ == "__main__":
    unittest.main()
