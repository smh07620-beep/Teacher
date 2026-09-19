from pathlib import Path
import unittest

from pgy_frontend import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class Phase3VAdminQuestionPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "admin-question-panel.js").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github" / "workflows" / "phase3-pgy-checks.yml").read_text(encoding="utf-8")

    def test_preserves_question_panel_globals(self):
        for name in (
            "updateManualQuestionType",
            "loadQuizQuestionCountOnly",
            "toggleQuizQuestionsPanel",
            "adminCreateQuizCategory",
            "adminDeleteQuizCategory",
        ):
            self.assertIn(f"window.{name}", self.source)

    def test_category_api_uses_session_rbac_without_admin_key(self):
        self.assertIn("fetch('/api/quiz-categories'", self.source)
        self.assertIn("/api/quiz-categories/${encodeURIComponent(catId)}", self.source)
        self.assertIn("method:'POST'", self.source)
        self.assertIn("method:'DELETE'", self.source)
        self.assertNotIn("X-Admin-Key", self.source)
        self.assertNotIn("getAdminKey", self.source)

    def test_panel_delegates_to_extracted_question_and_ai_modules(self):
        self.assertIn("window.loadQuizQuestionsIntoPanel(catId)", self.source)
        self.assertIn("window.loadAiMaterialOptions", self.source)
        self.assertIn("window.refreshAiQuestionStatus", self.source)
        self.assertIn("window.optimisticInsertQuizCategory", self.source)
        self.assertIn("window.renderAdminQuizCategories", self.source)

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

    def test_asset_loads_after_ai_runtime_and_is_syntax_checked(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertLess(body.index('/admin-ai-questions.js'), body.index('/admin-question-panel.js'))
        self.assertIn("find static -type f -name '*.js'", self.workflow)


if __name__ == "__main__":
    unittest.main()
