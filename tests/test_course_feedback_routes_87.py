import unittest
from unittest.mock import patch

from flask import Flask, g

from teacher_app.common.errors import ApiError
from teacher_app.learning import feedback_service
from teacher_app.learning.feedback_routes import register_course_feedback_routes


class CourseFeedbackRoutes87Tests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.user = {"username": "student.a", "role": "student", "roles": ["student"]}

        @self.app.before_request
        def bind_user():
            g.teacher_user = self.user

        register_course_feedback_routes(self.app)
        self.client = self.app.test_client()

    def test_get_put_and_summary_routes_are_registered(self):
        with patch.object(feedback_service, "get_own_feedback", return_value={"courseId": "c1", "feedback": None}) as getter:
            response = self.client.get("/api/course-feedback/c1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["courseId"], "c1")
        getter.assert_called_once()

        with patch.object(feedback_service, "submit_feedback", return_value={"ok": True, "courseId": "c1", "feedback": {"rating": 5}}) as submitter:
            response = self.client.put("/api/course-feedback/c1", json={"rating": 5, "comment": "good"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(submitter.call_args.args[2]["rating"], 5)

        with patch.object(feedback_service, "feedback_summary", return_value={"courseId": "c1", "responseCount": 2, "averageRating": 4.5}) as summary:
            response = self.client.get("/api/course-feedback/c1/summary")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["responseCount"], 2)
        summary.assert_called_once()

    def test_api_error_shape_is_preserved(self):
        with patch.object(feedback_service, "get_own_feedback", side_effect=ApiError("COURSE_NOT_FOUND", "找不到可存取的課程。", status=404)):
            response = self.client.get("/api/course-feedback/missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["code"], "COURSE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
