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
        for marker in (
            "__teacher66ReviewEditWrapped",
            "__teacher66ReviewRenderWrapped",
            "__teacher66ReviewSlidesWrapped",
            "__teacher66ReviewPageWrapped",
        ):
            self.assertIn(marker, self.review)
        self.assertGreaterEqual(self.review.count("original.apply("), 4)

    def test_teaching_wrappers_preserve_one_previous_implementation(self):
        for marker in (
            "teacher66OriginalSavePage",
            "teacher66OriginalMarkComplete",
            "teacher66OriginalNextMaterial",
            "teacher66OriginalSwitchCategory",
            "originalBuildCourseExamRow",
        ):
            self.assertIn(marker, self.teaching)
        self.assertNotIn("fetch('/api/material-progress'", self.teaching)

    def test_assessment_resilience_wraps_rendering_not_question_crud(self):
        self.assertIn("const canonicalQuizRender = window.renderAdminQuizCategories", self.resilience)
        self.assertIn("const canonicalPaint = window.paintAdminQuizCategories", self.resilience)
        self.assertIn("__teacher1014ScopeGuard", self.resilience)
        self.assertIn("__teacher1014EmptyRecovery", self.resilience)
        self.assertNotIn("adminBuildQuestionPayload =", self.resilience)


if __name__ == "__main__":
    unittest.main()
