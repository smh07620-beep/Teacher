import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class CourseFeedbackUi87Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath("static", "system.html").read_text(encoding="utf-8")
        cls.learner = ROOT.joinpath("static", "system-learner.js").read_text(encoding="utf-8")
        cls.admin = ROOT.joinpath("static", "admin-course-material.js").read_text(encoding="utf-8")
        cls.factory = ROOT.joinpath("teacher_app", "factory.py").read_text(encoding="utf-8")

    def test_feedback_dialog_is_named_and_has_programmatic_labels(self):
        for token in (
            'id="course-feedback-dialog" aria-label="課程回饋"',
            'for="course-feedback-rating"',
            'id="course-feedback-rating"',
            'for="course-feedback-comment"',
            'id="course-feedback-comment"',
            'id="course-feedback-status" role="status"',
        ):
            self.assertIn(token, self.html)

    def test_learner_runtime_loads_and_updates_own_feedback(self):
        for token in (
            "openCourseFeedback(course.id",
            "/api/course-feedback/${encodeURIComponent(courseId)}",
            "method:'PUT'",
            "bindCourseFeedbackUI()",
            "回饋已儲存",
        ):
            self.assertIn(token, self.learner)

    def test_feedback_runtime_is_cache_busted_and_registered(self):
        self.assertIn('system-learner.js?v=9000', self.html)
        self.assertIn("register_course_feedback_routes", self.factory)
        self.assertNotIn('data-csp-click="openCourseFeedback', self.html)

    def test_admin_workspace_shows_only_aggregate_feedback(self):
        for token in (
            "/api/course-feedback/${encodeURIComponent(courseId)}/summary",
            "課程回饋彙總",
            "averageRating",
            "ratingCounts",
            "只顯示匿名統計",
        ):
            self.assertIn(token, self.admin)
        self.assertNotIn("data-course-feedback-username", self.admin)
        self.assertNotIn("data-course-feedback-comment", self.admin)

if __name__ == "__main__":
    unittest.main()
