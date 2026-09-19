from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RuntimeConvergence74Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.advanced = (ROOT / "static" / "assessment-advanced-74.js").read_text(encoding="utf-8")
        cls.system = (ROOT / "static" / "system.html").read_text(encoding="utf-8")
        cls.bank = (ROOT / "static" / "admin-question-bank.js").read_text(encoding="utf-8")
        cls.editor = (ROOT / "static" / "admin-question-editor-ui.js").read_text(encoding="utf-8")
        cls.actions = (ROOT / "static" / "admin-question-actions.js").read_text(encoding="utf-8")
        cls.panel = (ROOT / "static" / "admin-question-panel.js").read_text(encoding="utf-8")
        cls.exam_settings = (ROOT / "static" / "admin-exam-settings.js").read_text(encoding="utf-8")
        cls.ai = (ROOT / "static" / "admin-ai-questions.js").read_text(encoding="utf-8")
        cls.audit = (ROOT / "RUNTIME_CONVERGENCE_AUDIT_74.md").read_text(encoding="utf-8")
        cls.architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")

    def test_legacy_assessment_application_is_physically_removed(self):
        self.assertFalse((ROOT / "static" / "assessment-681.js").exists())
        self.assertIn('/assessment-advanced-74.js?v=7400', self.system)

    def test_old_question_drawer_overlay_is_physically_removed(self):
        self.assertFalse((ROOT / "static" / "question-authoring-ux-71.js").exists())

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
        self.assertIn("`static/admin-compat-facade.js`, `static/assessment-681.js`, `static/question-authoring-ux-71.js`, and `static/runtime-escape-guard-7111.js` are removed", self.architecture)
        self.assertIn("`static/assessment-advanced-74.js`", self.architecture)
        self.assertIn("one normal user-facing runtime owner per responsibility", self.audit)
        self.assertIn("compatibility assets are physically removed", self.audit)


if __name__ == "__main__":
    unittest.main()
