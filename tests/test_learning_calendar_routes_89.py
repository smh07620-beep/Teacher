import unittest
from unittest.mock import patch
from flask import Flask, g
from teacher_app.learning import calendar_service
from teacher_app.learning.calendar_routes import register_learning_calendar_routes

class LearningCalendarRoutes89Tests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.user = {"username": "student.a", "empId": "E001", "name": "Student A", "role": "student"}
        @self.app.before_request
        def bind_user(): g.teacher_user = self.user
        register_learning_calendar_routes(self.app)
        self.client = self.app.test_client()

    def test_calendar_route_passes_request_to_service(self):
        payload = {"events": [], "counts": {"total": 0, "overdue": 0, "upcoming": 0}, "windowDays": 30}
        with patch.object(calendar_service, "calendar_summary", return_value=payload) as summary:
            response = self.client.get("/api/learning-calendar?days=30")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["windowDays"], 30)
        self.assertEqual(summary.call_args.kwargs["days"], 30)

    def test_invalid_days_returns_400(self):
        response = self.client.get("/api/learning-calendar?days=abc")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "INVALID_CALENDAR_RANGE")

if __name__ == "__main__": unittest.main()
