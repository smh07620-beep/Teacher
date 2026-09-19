from pathlib import Path
import unittest

from pgy_frontend import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class Phase3QAdminResultsExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "admin-results-export.js").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github" / "workflows" / "phase3-pgy-checks.yml").read_text(encoding="utf-8")

    def test_preserves_results_export_global_contracts(self):
        for name in (
            "buildRoleCheckboxText",
            "buildEvaluatorTitleCheckboxText",
            "buildCurrentTabDocPayload",
            "buildRecordDocPayload",
            "renderDocxFromBuffer",
            "exportWithServerTemplate",
            "exportRecordToWord",
            "exportToCSV",
        ):
            self.assertIn(f"window.{name}", self.source)

    def test_docx_server_template_contract_stays_intact(self):
        self.assertIn("/api/doc-templates/${groupKey}/download", self.source)
        self.assertIn("window.docxtemplater", self.source)
        self.assertIn("PizZip", self.source)
        self.assertIn("saveAs", self.source)
        self.assertIn("附件1.${filenamePart}.docx", self.source)

    def test_csv_export_contract_stays_intact(self):
        self.assertIn("fetchAdminRecords", self.source)
        self.assertIn("text/csv;charset=utf-8", self.source)
        self.assertIn("考核時間,組別,姓名,工號", self.source)
        self.assertIn("教育訓練考核成績表_", self.source)

    def test_local_docx_fallback_is_owned_by_export_runtime(self):
        self.assertIn("docx-template-input", self.source)
        self.assertIn("cachedTemplateBuffer", self.source)
        self.assertIn("pendingExportRecordIndex", self.source)
        legacy = (ROOT / "static" / "system-admin.js").read_text(encoding="utf-8")
        self.assertNotIn("docx-template-input", legacy)
        self.assertNotIn("cachedTemplateBuffer", legacy)
        self.assertNotIn("pendingExportRecordIndex", legacy)

    def test_module_does_not_redefine_rbac_or_profile_metadata_as_policy(self):
        for forbidden in (
            "professional_title",
            "responsibility_tags",
            "professionalTitle",
            "responsibilityTags",
            "hasPermission",
            "canOpenWorkspace",
            "data-admin-role",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_asset_is_injected_and_checked_by_release_workflow(self):
        self.assertIn('/admin-results-export.js', ASSET_MANIFEST["system"]["body"])
        self.assertIn("find static -type f -name '*.js'", self.workflow)


if __name__ == "__main__":
    unittest.main()
