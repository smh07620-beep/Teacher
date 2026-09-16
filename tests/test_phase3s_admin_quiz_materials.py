from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Phase3SAdminQuizMaterialsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "admin-quiz-materials.js").read_text(encoding="utf-8")
        cls.frontend = (ROOT / "pgy_frontend.py").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github" / "workflows" / "phase3-pgy-checks.yml").read_text(encoding="utf-8")

    def test_preserves_quiz_material_linker_globals(self):
        for name in (
            "openQuizMaterialLinker",
            "closeQuizMaterialLinker",
            "renderQuizMaterialLinker",
            "filterQuizMaterialLinker",
            "saveQuizMaterialLinks",
        ):
            self.assertIn(f"window.{name}", self.source)

    def test_material_link_api_and_admin_key_contract_stay_intact(self):
        self.assertIn("/api/quiz-categories/${catId}/materials", self.source)
        self.assertIn("method:'PUT'", self.source)
        self.assertIn("'X-Admin-Key':key", self.source)
        self.assertIn("materialIds:ids", self.source)
        self.assertIn("invalidateAdminMaterialsCache", self.source)

    def test_module_keeps_ai_refresh_as_runtime_integration_only(self):
        self.assertIn("window.loadAiMaterialOptions", self.source)
        self.assertNotIn("aiMaterialCatalog", self.source)
        self.assertNotIn("aiQuestionDrafts", self.source)

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
        marker = '<script defer src="/admin-quiz-materials.js?v=7118"></script>'
        self.assertIn(marker, self.frontend)
        self.assertIn("node --check static/admin-quiz-materials.js", self.workflow)


if __name__ == "__main__":
    unittest.main()
