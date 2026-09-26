import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LearningCalendarUi89Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath("static", "system.html").read_text(encoding="utf-8")
        cls.learner = ROOT.joinpath("static", "system-learner.js").read_text(encoding="utf-8")
        cls.factory = ROOT.joinpath("teacher_app", "factory.py").read_text(encoding="utf-8")

    def test_calendar_surface_is_present(self):
        self.assertIn('id="learning-calendar"', self.html)
        self.assertIn('id="learning-calendar-list"', self.html)
        self.assertIn('/system-learner.js?v=9000', self.html)

    def test_calendar_runtime_fetches_and_routes_events(self):
        self.assertIn("fetch('/api/learning-calendar?days=90'", self.learner)
        self.assertIn("function renderLearningCalendar()", self.learner)
        self.assertIn("function openLearningCalendarEvent(eventId)", self.learner)

    def test_factory_registers_calendar_routes(self):
        self.assertIn("from teacher_app.learning.calendar_routes import register_learning_calendar_routes", self.factory)
        self.assertIn("app = register_learning_calendar_routes(app)", self.factory)


if __name__ == "__main__":
    unittest.main()
