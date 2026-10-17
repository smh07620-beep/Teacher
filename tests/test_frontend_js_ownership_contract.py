from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrontendJsOwnershipContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = (ROOT / "docs" / "FRONTEND_JS_OWNERSHIP.md").read_text(encoding="utf-8")
        cls.teaching = (ROOT / "static" / "teaching.js").read_text(encoding="utf-8")
        cls.review = (ROOT / "static" / "review-links-66.js").read_text(encoding="utf-8")
        cls.resilience = (ROOT / "static" / "teacher-ui-resilience-1014.js").read_text(encoding="utf-8")

    def test_classic_script_wrappers_are_part_of_the_ownership_map(self):
        for name in (
            "adminQuestionEditFormHTML",
            "renderQuestions",
            "renderSlidesGrid",
            "teachingSavePage",
            "teachingNextMaterial",
            "switchDynamicCategory",
            "buildCourseExamRow",
            "renderAdminQuizCategories",
            "paintAdminQuizCategories",
        ):
            self.assertIn(name, self.doc)

    def test_review_link_wrappers_are_guarded_and_call_the_previous_owner(self):
        # 2026-10-17: review links listen to owner events and expose helpers; no wrappers remain.
        self.assertEqual(self.review.count("original.apply("), 0)
        for marker in ("teacher:exam-rendered", "teacher:learner-rendered", "teacher:reader-changed", "editorBlock(question)"):
            self.assertIn(marker, self.review)

    def test_teaching_wrappers_preserve_one_previous_implementation(self):
        # 2026-10-17: teaching.js wraps nothing; it exposes helpers its owners call.
        self.assertNotIn("teacher66Original", self.teaching)
        self.assertIn("window.TeachingIdentity = Object.freeze", self.teaching)
        # 2026-10-17: the exam row is rendered by its owner; no wrapper chain on buildCourseExamRow.
        self.assertNotIn("originalBuildCourseExamRow", self.teaching)
        self.assertNotIn("teacher66OriginalSwitchCategory", self.teaching)
        self.assertIn("window.TeachingEmptyExam = Object.freeze", self.teaching)
        self.assertNotIn("fetch('/api/material-progress'", self.teaching)

    def test_assessment_resilience_wraps_rendering_not_question_crud(self):
        # 2026-10-17: the owner calls TeacherAssessmentScope.sync and announces its paint.
        self.assertIn("window.TeacherAssessmentScope = Object.freeze({ sync: syncAssessmentScope })", self.resilience)
        self.assertIn("view === 'quiz-categories'", self.resilience)
        self.assertNotIn("window.renderAdminQuizCategories = guarded", self.resilience)
        self.assertNotIn("window.paintAdminQuizCategories = painted", self.resilience)
        self.assertNotIn("adminBuildQuestionPayload =", self.resilience)


if __name__ == "__main__":
    unittest.main()
