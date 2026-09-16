from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Phase3TAdminQuestionEditorUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "admin-question-editor-ui.js").read_text(encoding="utf-8")
        cls.frontend = (ROOT / "pgy_frontend.py").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github" / "workflows" / "phase3-pgy-checks.yml").read_text(encoding="utf-8")

    def test_preserves_question_editor_ui_globals(self):
        for name in (
            "adminAnswerSummary",
            "adminQuestionEditFormHTML",
            "adminInlineQuestionTypeChanged",
            "adminQuestionRowHTML",
            "adminSelectedQuestionIds",
            "adminUpdateQuestionSelection",
            "adminSelectAllQuestions",
            "adminToggleInlineQuestionEditor",
            "adminEditSelectedQuestions",
            "renderFilteredQuestionList",
        ):
            self.assertIn(f"window.{name}", self.source)

    def test_keeps_mutation_actions_as_existing_runtime_contracts(self):
        for onclick in (
            "adminSaveOneInlineQuestion",
            "adminToggleQuizQuestion",
            "adminDeleteQuizQuestion",
        ):
            self.assertIn(onclick, self.source)
        self.assertNotIn("fetch('/api/quiz-questions'", self.source)
        self.assertNotIn("method:'PATCH'", self.source)
        self.assertNotIn("method:'DELETE'", self.source)

    def test_uses_shared_question_cache_without_redeclaring_it(self):
        self.assertIn("adminQuizQuestionCache[catId]", self.source)
        self.assertNotIn("const adminQuizQuestionCache", self.source)
        self.assertNotIn("let adminQuizQuestionCache", self.source)

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
        marker = '<script defer src="/admin-question-editor-ui.js?v=7119"></script>'
        self.assertIn(marker, self.frontend)
        self.assertIn("node --check static/admin-question-editor-ui.js", self.workflow)


if __name__ == "__main__":
    unittest.main()
