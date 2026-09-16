from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Phase3WLearnerExamControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "learner-exam-controls.js").read_text(encoding="utf-8")
        cls.frontend = (ROOT / "pgy_frontend.py").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github" / "workflows" / "phase3-pgy-checks.yml").read_text(encoding="utf-8")

    def test_preserves_learner_html_and_runtime_globals(self):
        self.assertIn("window.resetCurrentQuiz", self.source)
        self.assertIn("window.toggleSopModal", self.source)

    def test_reset_preserves_learner_draft_and_progress_contracts(self):
        for contract in (
            "isSubmittedMap[currentCatKey] = false",
            "userAnswersMap[currentCatKey]",
            "flaggedQuestionsMap[currentCatKey]",
            "clearExamDraft(currentCatKey)",
            "saveExamDraft(currentCatKey)",
            "renderQuestions()",
            "updateProgressStats()",
        ):
            self.assertIn(contract, self.source)

    def test_module_does_not_introduce_admin_api_or_rbac_policy(self):
        for forbidden in ("fetch(", "getAdminKey", "X-Admin-Key", "professional_title", "responsibility_tags", "hasPermission"):
            self.assertNotIn(forbidden, self.source)

    def test_asset_is_injected_and_syntax_checked(self):
        marker = '<script defer src="/learner-exam-controls.js?v=7122"></script>'
        self.assertIn(marker, self.frontend)
        self.assertIn("node --check static/learner-exam-controls.js", self.workflow)


if __name__ == "__main__":
    unittest.main()
