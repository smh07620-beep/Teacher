"""Course accordion clarity (2026-10-10): contract for the learner course list."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CourseAccordionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.teaching = (ROOT / "static/teaching.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "static/learner.css").read_text(encoding="utf-8")
        cls.html = (ROOT / "static/system.html").read_text(encoding="utf-8")

    def test_summary_shows_text_label_chevron_and_state_badge(self):
        for marker in (
            'class="when-closed">展開',
            'class="when-open">收合',
            "badge(done ? 'doing' : 'todo'",
            "course-state-${tone}",
            "未開始",
            "學習中",
            "教材已完成",
            "待評核",
            "未通過需補訓",
        ):
            self.assertIn(marker, self.teaching)
        self.assertIn("course-learning-chevron", self.teaching)

    def test_state_badge_uses_exam_result(self):
        loop = (ROOT / "static/learner-study-exam-loop-1032.js").read_text(encoding="utf-8")
        self.assertIn("window.LearnerExamStatus = Object.freeze", loop)
        self.assertIn("window.LearnerExamStatus?.get?.(exam.id)", self.teaching)
        self.assertIn("function teachingCourseStateBadge(", self.teaching)

    def test_only_one_unit_open_and_first_unfinished_is_default(self):
        self.assertIn("function collapseOthers(card)", self.teaching)
        self.assertIn("other.open = false", self.teaching)
        self.assertIn("const firstTodo = courses.find(", self.teaching)
        self.assertIn("followRecommended", self.teaching)
        self.assertNotIn("hadCards", self.teaching)

    def test_opened_unit_scrolls_into_view_and_respects_reduced_motion(self):
        self.assertIn("scrollIntoView({behavior: reduceMotion() ? 'auto' : 'smooth'", self.teaching)
        self.assertIn("prefers-reduced-motion", self.teaching)

    def test_next_step_lives_in_my_todo_not_a_second_button(self):
        self.assertNotIn("course-continue", self.html)
        self.assertNotIn("teachingUpdateContinueButton", self.teaching)
        self.assertIn("window.Teacher71LearnerTasks", self.teaching)
        self.assertIn("teacher71:learner-tasks", self.teaching)
        command = (ROOT / "static/training-command-center-71.js").read_text(encoding="utf-8")
        self.assertIn("window.Teacher71LearnerTasks = Object.freeze", command)
        self.assertIn("📌 我的待辦", command)
        self.assertIn('id="training-command-toggle-71"', command)

    def test_unit_rows_show_deadline_and_shelves_follow_the_course_list(self):
        self.assertIn("course-due-overdue", self.teaching)
        grid = self.html.index('id="course-overview-grid"')
        self.assertLess(grid, self.html.index('id="saved-learning-items"'))
        self.assertLess(grid, self.html.index('id="completion-certificates"'))

    def test_open_unit_title_is_sticky(self):
        self.assertIn(".course-learning-card[open]>.course-learning-summary{position:sticky", self.css)
        self.assertIn("#course-overview .course-learning-card{overflow:clip", self.css)


if __name__ == "__main__":
    unittest.main()
