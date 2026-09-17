from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RuntimeConvergence74Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compat = (ROOT / "static" / "assessment-681.js").read_text(encoding="utf-8")
        cls.retired_authoring = (ROOT / "static" / "question-authoring-ux-71.js").read_text(encoding="utf-8")
        cls.advanced = (ROOT / "static" / "assessment-advanced-74.js").read_text(encoding="utf-8")
        cls.bank = (ROOT / "static" / "admin-question-bank.js").read_text(encoding="utf-8")
        cls.editor = (ROOT / "static" / "admin-question-editor-ui.js").read_text(encoding="utf-8")
        cls.actions = (ROOT / "static" / "admin-question-actions.js").read_text(encoding="utf-8")
        cls.panel = (ROOT / "static" / "admin-question-panel.js").read_text(encoding="utf-8")
        cls.exam_settings = (ROOT / "static" / "admin-exam-settings.js").read_text(encoding="utf-8")
        cls.ai = (ROOT / "static" / "admin-ai-questions.js").read_text(encoding="utf-8")
        cls.audit = (ROOT / "RUNTIME_CONVERGENCE_AUDIT_74.md").read_text(encoding="utf-8")
        cls.architecture = (ROOT / "ARCHITECTURE_FINAL_CONVERGENCE.md").read_text(encoding="utf-8")

    def test_legacy_assessment_application_is_not_a_second_ui(self):
        for forbidden in (
            "legacy.classList.add('hidden')",
            "insertAdjacentHTML",
            "assessment-681-body",
            "assessment-681-tabs",
            "question-bank-drawer",
            "function examsHTML",
            "function bankHTML",
            "function aiHTML",
            "function openQuestion",
            "function saveQuestion",
            "function createAiDrafts",
        ):
            self.assertNotIn(forbidden, self.compat)

    def test_assessment_compatibility_router_has_no_api_or_mutation_logic(self):
        for forbidden in (
            "fetch(", "/api/", "method:'POST'", "method:'PATCH'", "method:'DELETE'",
            "X-Admin-Key", "getAdminKey",
        ):
            self.assertNotIn(forbidden, self.compat)
        self.assertIn("renderAdminQuizCategories", self.compat)
        self.assertIn("AssessmentAdvanced74", self.compat)

    def test_old_question_drawer_overlay_is_retired(self):
        self.assertIn("Retired by Teacher runtime convergence", self.retired_authoring)
        for forbidden in ("qb681-", "fetch(", "/api/", "assessment681Delete", "assessment681SaveQuestion"):
            self.assertNotIn(forbidden, self.retired_authoring)

    def test_unique_advanced_owner_does_not_reimplement_crud_or_ai(self):
        self.assertIn("/api/exam-blueprints", self.advanced)
        self.assertIn("/api/questions/", self.advanced)
        self.assertIn("credentials:'same-origin'", self.advanced)
        for forbidden in (
            "/api/ai-questions/generate",
            "/api/question-bank/drafts",
            "/api/quiz-questions/",
            "adminAddQuizQuestion",
            "adminDeleteQuizQuestion",
        ):
            self.assertNotIn(forbidden, self.advanced)

    def test_canonical_owner_stack_keeps_all_management_capabilities(self):
        self.assertIn("renderAdminQuizCategories", self.bank)
        self.assertIn("adminQuestionEditFormHTML", self.editor)
        self.assertIn("adminDeleteQuizQuestion", self.actions)
        self.assertIn("adminBulkDeleteQuestions", self.actions)
        self.assertIn("adminCreateQuizCategory", self.panel)
        self.assertIn("adminDeleteQuizCategory", self.panel)
        self.assertIn("adminEditQuizCategory", self.exam_settings)
        self.assertIn("adminGenerateAiQuestions", self.ai)
        self.assertIn("adminImportAiCandidates", self.ai)

    def test_architecture_and_audit_freeze_single_runtime_ownership(self):
        self.assertIn("`static/assessment-681.js` is compatibility routing only", self.architecture)
        self.assertIn("`static/question-authoring-ux-71.js` is a retired compatibility marker", self.architecture)
        self.assertIn("`static/assessment-advanced-74.js`", self.architecture)
        self.assertIn("one normal user-facing runtime owner per responsibility", self.audit)
        self.assertIn("The visible `assessment-681` application is retired", self.audit)


if __name__ == "__main__":
    unittest.main()
