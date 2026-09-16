from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Phase3NAdminDocTemplatesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "admin-doc-templates.js").read_text(encoding="utf-8")
        cls.frontend = (ROOT / "pgy_frontend.py").read_text(encoding="utf-8")

    def test_preserves_document_template_globals_and_onclick_contracts(self):
        for name in ("renderAdminDocTemplates", "adminTriggerDocTemplateUpload", "adminDeleteDocTemplate"):
            self.assertIn(f"window.{name}", self.source)
        self.assertIn("admin-doc-template-upload-input", self.source)
        self.assertIn("uploadTemplate, true", self.source)
        self.assertIn("onclick=\"adminTriggerDocTemplateUpload", self.source)
        self.assertIn("onclick=\"adminDeleteDocTemplate", self.source)

    def test_template_api_and_admin_key_contract_stay_intact(self):
        for endpoint in ("/api/doc-templates", "/api/doc-templates/${groupKey}"):
            self.assertIn(endpoint, self.source)
        self.assertIn("'X-Admin-Key':key", self.source)
        self.assertIn("method:'POST'", self.source)
        self.assertIn("method:'DELETE'", self.source)

    def test_module_does_not_redefine_rbac_or_permission_policy(self):
        for forbidden in ("professionalTitle", "responsibilityTags", "hasPermission", "data-admin-role"):
            self.assertNotIn(forbidden, self.source)

    def test_loads_after_legacy_bundle_and_before_workflow_wrappers(self):
        marker = 'doc_templates_marker = \'<script defer src="/admin-doc-templates.js?v=7113"></script>\''
        self.assertIn(marker, self.frontend)
        self.assertIn('replacement += "\\n" + doc_templates_marker', self.frontend)
        self.assertLess(self.frontend.index("admin-doc-templates.js"), self.frontend.index("/pgy-workflow.js"))


if __name__ == "__main__":
    unittest.main()
