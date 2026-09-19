from pathlib import Path
import unittest

from pgy_frontend import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class Phase3SAdminQuizMaterialsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "admin-quiz-materials.js").read_text(encoding="utf-8")
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

    def test_material_link_api_uses_session_rbac_without_admin_key(self):
        self.assertIn("/api/quiz-categories/${catId}/materials", self.source)
        self.assertIn("method:'PUT'", self.source)
        self.assertNotIn("X-Admin-Key", self.source)
        self.assertNotIn("getAdminKey", self.source)
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
        self.assertIn('/admin-quiz-materials.js', ASSET_MANIFEST["system"]["body"])
        self.assertIn("find static -type f -name '*.js'", self.workflow)


if __name__ == "__main__":
    unittest.main()
