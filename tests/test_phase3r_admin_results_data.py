from pathlib import Path
import unittest

from pgy_frontend import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class Phase3RAdminResultsDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "admin-results-data.js").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github" / "workflows" / "phase3-pgy-checks.yml").read_text(encoding="utf-8")

    def test_preserves_results_data_globals(self):
        for name in (
            "renderResultsAnalytics",
            "fetchAdminRecords",
            "adminResultDetail",
            "renderAdminTable",
            "clearAllRecords",
        ):
            self.assertIn(f"window.{name}", self.source)

    def test_records_api_and_admin_key_contract_stay_intact(self):
        self.assertIn("fetch('/api/records'", self.source)
        self.assertIn("method:'DELETE'", self.source)
        self.assertIn("'X-Admin-Key':key", self.source)
        self.assertIn("adminRecords=", self.source)

    def test_results_workspace_state_remains_in_wrapper(self):
        self.assertNotIn("adminResultWorkspaceMode", self.source)
        self.assertNotIn("teacherWorkspaceMode", self.source)
        self.assertIn("window.updateResultsWorkspacePresentation?.()", self.source)
        self.assertIn("window.fetchAdminRecords()", self.source)
        self.assertIn("window.renderResultsAnalytics(records)", self.source)

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

    def test_load_order_allows_results_mode_to_wrap_extracted_data_runtime(self):
        ordered = dict(ASSET_MANIFEST["system"]["ordered"])["/system-admin.js"]
        self.assertLess(ordered.index("/admin-results-data.js"), ordered.index("/admin-results-workspace.js"))
        self.assertIn("find static -type f -name '*.js'", self.workflow)


if __name__ == "__main__":
    unittest.main()
