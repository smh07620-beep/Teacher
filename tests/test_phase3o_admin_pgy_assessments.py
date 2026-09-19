from pathlib import Path
import unittest

from pgy_frontend import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class Phase3OAdminPgyAssessmentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "admin-pgy-assessments.js").read_text(encoding="utf-8")
        cls.clinical_source = (ROOT / "static" / "system-assessment.js").read_text(encoding="utf-8")
        cls.ordered = dict(ASSET_MANIFEST["system"]["ordered"])["/system-admin.js"]

    def test_preserves_pgy_admin_globals_and_onclick_contracts(self):
        for name in (
            "renderAdminPgyTemplates",
            "adminTriggerPgyTemplateUpload",
            "adminDeletePgyTemplate",
            "adminImportTslmEpa",
            "renderAdminPgyAssessments",
        ):
            self.assertIn(f"window.{name}", self.source)
        self.assertIn('data-csp-click="adminTriggerPgyTemplateUpload', self.source)
        self.assertIn('data-csp-click="adminDeletePgyTemplate', self.source)
        self.assertIn("admin-pgy-template-upload-input", self.source)

    def test_template_and_assessment_api_contracts_remain_server_authorized(self):
        for endpoint in (
            "/api/pgy-assessment-templates",
            "/api/pgy-assessment-templates/${type}",
            "/api/pgy-assessment-templates/import-tslm-epa",
            "/api/pgy-assessments",
        ):
            self.assertIn(endpoint, self.source)
        self.assertNotIn("X-Admin-Key", self.source)
        self.assertNotIn("getAdminKey", self.source)
        self.assertIn("method:'POST'", self.source)
        self.assertIn("method:'DELETE'", self.source)

    def test_module_does_not_redefine_rbac_or_profile_fields_as_permissions(self):
        for forbidden in ("professionalTitle", "responsibilityTags", "hasPermission", "data-admin-role"):
            self.assertNotIn(forbidden, self.source)

    def test_loads_after_legacy_bundle_and_before_workflow_wrappers(self):
        self.assertIn('/admin-pgy-assessments.js', self.ordered)

    def test_clinical_assessment_bundle_no_longer_duplicates_admin_runtime(self):
        self.assertIn("function renderPgyAssessmentForm", self.clinical_source)
        self.assertIn("async function submitPgyAssessment", self.clinical_source)
        for name in (
            "renderAdminPgyTemplates",
            "adminTriggerPgyTemplateUpload",
            "adminDeletePgyTemplate",
            "adminImportTslmEpa",
            "renderAdminPgyAssessments",
        ):
            self.assertNotIn(name, self.clinical_source)


if __name__ == "__main__":
    unittest.main()
