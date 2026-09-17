"""Loaded-browser contracts complement the route-level workflow tests."""
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class FeatureExposureUi681Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assessment_compat = ROOT.joinpath("static", "assessment-681.js").read_text(encoding="utf-8")
        cls.advanced = ROOT.joinpath("static", "assessment-advanced-74.js").read_text(encoding="utf-8")
        cls.question_bank = ROOT.joinpath("static", "admin-question-bank.js").read_text(encoding="utf-8")
        cls.question_actions = ROOT.joinpath("static", "admin-question-actions.js").read_text(encoding="utf-8")
        cls.exam_settings = ROOT.joinpath("static", "admin-exam-settings.js").read_text(encoding="utf-8")
        cls.ai_questions = ROOT.joinpath("static", "admin-ai-questions.js").read_text(encoding="utf-8")
        cls.wizard = ROOT.joinpath("static", "course-wizard-681.js").read_text(encoding="utf-8")
        cls.external = ROOT.joinpath("static", "external-material-681.js").read_text(encoding="utf-8")
        cls.media = ROOT.joinpath("static", "smart-learning-67.js").read_text(encoding="utf-8")

    def test_assessment_compatibility_file_no_longer_owns_second_ui_or_mutations(self):
        self.assertIn("Compatibility router after Teacher runtime convergence", self.assessment_compat)
        self.assertIn("admin-question-bank.js", self.assessment_compat)
        self.assertIn("admin-question-actions.js", self.assessment_compat)
        self.assertIn("admin-ai-questions.js", self.assessment_compat)
        for forbidden in (
            "assessment-681-body",
            "question-bank-drawer",
            "function examsHTML",
            "function bankHTML",
            "function createAiDrafts",
            "/api/question-bank/drafts",
            "/api/ai-questions/generate",
            "method:'PATCH'",
            "method:'DELETE'",
        ):
            self.assertNotIn(forbidden, self.assessment_compat)

    def test_unique_blueprint_and_analytics_capabilities_have_one_advanced_owner(self):
        self.assertIn("Advanced assessment tools only", self.advanced)
        self.assertIn("/api/exam-blueprints", self.advanced)
        self.assertIn("/api/questions/", self.advanced)
        self.assertIn("出題藍圖", self.advanced)
        self.assertIn("題目分析", self.advanced)
        for forbidden in (
            "/api/ai-questions/generate",
            "/api/question-bank/drafts",
            "/api/quiz-questions/",
            "adminAddQuizQuestion",
            "adminDeleteQuizQuestion",
        ):
            self.assertNotIn(forbidden, self.advanced)

    def test_exam_question_and_ai_mutations_stay_with_canonical_admin_owners(self):
        self.assertIn("renderAdminQuizCategories", self.question_bank)
        self.assertIn("adminDeleteQuizQuestion", self.question_actions)
        self.assertIn("adminBulkDeleteQuestions", self.question_actions)
        self.assertIn("adminEditQuizCategory", self.exam_settings)
        self.assertIn("adminGenerateAiQuestions", self.ai_questions)
        self.assertIn("adminImportAiCandidates", self.ai_questions)

    def test_stepper_preserves_files_and_supports_all_exam_choices(self):
        self.assertIn("state.files", self.wizard)
        for choice in ("稍後建立", "從題庫選", "AI 草稿", "Blueprint"):
            self.assertIn(choice, self.wizard)
        self.assertIn("MaterialUploadClient.enqueue", self.wizard)
        self.assertNotIn("/api/slides/upload", self.wizard)

    def test_external_creation_has_no_storage_or_worker_caller(self):
        self.assertIn("/api/materials/external", self.external)
        for forbidden in ("/api/material-jobs", "/api/r2", "/api/mega", "<iframe"):
            self.assertNotIn(forbidden, self.external.lower())

    def test_canonical_media_tracks_coverage_and_review_seek(self):
        for marker in ("watchedBuckets", "completionThreshold:.9", "teacher681SeekReviewSource",
                       "youtube-nocookie.com", "/external-media"):
            self.assertIn(marker, self.media)


if __name__ == "__main__":
    unittest.main()
