import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LearningCalendarUi89Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath("static", "system.html").read_text(encoding="utf-8")
        cls.learner = ROOT.joinpath("static", "system-learner.js").read_text(encoding="utf-8")
        cls.factory = ROOT.joinpath("teacher_app", "factory.py").read_text(encoding="utf-8")

    def test_calendar_panel_is_folded_into_my_todo(self):
        # 2026-10-10: course deadlines come from the same dashboard data as the
        # learner to-do list, so the separate calendar panel was removed; deadlines
        # now show in 我的待辦 and on each course row. The API itself stays.
        self.assertNotIn('id="learning-calendar"', self.html)
        self.assertNotIn("fetch('/api/learning-calendar", self.learner)
        self.assertNotIn("renderLearningCalendar", self.learner)
        self.assertIn('/system-learner.js?v=9000', self.html)

    def test_factory_registers_calendar_routes(self):
        self.assertIn("from teacher_app.learning.calendar_routes import register_learning_calendar_routes", self.factory)
        self.assertIn("app = register_learning_calendar_routes(app)", self.factory)


if __name__ == "__main__":
    unittest.main()
