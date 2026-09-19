from pathlib import Path
import unittest

from pgy_frontend import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class Phase3UAdminQuestionActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "admin-question-actions.js").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github" / "workflows" / "phase3-pgy-checks.yml").read_text(encoding="utf-8")

    def test_preserves_question_mutation_globals(self):
        for name in (
            "adminBuildQuestionPayload",
            "setQuestionRowBusy",
            "setQuestionBulkBusy",
            "updateQuestionCacheAndPaint",
            "loadQuizQuestionsIntoPanel",
            "adminSaveOneInlineQuestion",
            "adminToggleQuizQuestion",
            "adminDeleteQuizQuestion",
            "adminBulkSetQuestionActive",
            "adminBulkTagQuestions",
            "adminBulkDeleteQuestions",
            "adminImportQuizUrl",
            "adminAddQuizQuestion",
        ):
            self.assertIn(f"window.{name}", self.source)

    def test_question_api_contracts_stay_intact(self):
        for endpoint in (
            "/api/quiz-questions/admin?category=",
            "/api/quiz-questions/${encodeURIComponent(qId)}",
            "/api/quiz-questions/import-url",
            "/api/quiz-question-images",
            "fetch('/api/quiz-questions'",
        ):
            self.assertIn(endpoint, self.source)
        self.assertNotIn("X-Admin-Key", self.source)
        self.assertNotIn("getAdminKey", self.source)
        self.assertIn("method:'PATCH'", self.source)
        self.assertIn("method:'DELETE'", self.source)
        self.assertIn("method:'POST'", self.source)

    def test_uses_shared_question_cache_and_ui_module_contracts(self):
        self.assertIn("adminQuizQuestionCache[catId]", self.source)
        self.assertNotIn("const adminQuizQuestionCache", self.source)
        self.assertIn("window.renderFilteredQuestionList(catId)", self.source)
        self.assertIn("window.adminSelectedQuestionIds(catId)", self.source)

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

    def test_asset_loads_after_question_editor_ui_and_is_syntax_checked(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertLess(body.index('/admin-question-editor-ui.js'), body.index('/admin-question-actions.js'))
        self.assertIn("find static -type f -name '*.js'", self.workflow)


if __name__ == "__main__":
    unittest.main()
