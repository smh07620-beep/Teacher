import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from teacher_app.command_center import analytics
from teacher_app.command_center.routes import register_training_command_center
from teacher_app.common.errors import ApiError


class TeacherAnalyticsP2Tests(unittest.TestCase):
    def test_teacher_scoped_roles_reuse_canonical_learning_analytics(self):
        expected = {
            "scope": {"kind": "assigned"},
            "summary": {"learners": 1},
            "learners": [],
            "timeline": [],
        }
        users = [
            {"username": "teacher1", "role": "clinical_teacher", "roles": ["clinical_teacher"], "preferredGroup": "grpBio"},
            {"username": "leader1", "role": "group_leader", "roles": ["group_leader"], "preferredGroup": "grpBio"},
            {"username": "edu1", "role": "education_admin", "roles": ["education_admin"], "preferredGroup": "grpBio"},
        ]
        for user in users:
            with self.subTest(role=user["role"]), patch.object(
                analytics, "build_learning_analytics", return_value=dict(expected)
            ) as build:
                data = analytics.build_teacher_analytics(user)
            build.assert_called_once_with(user, now=None)
            self.assertEqual(data["source"], "scoped-learning-exam-pgy-records")
            self.assertEqual(data["interpretation"], "descriptive_teacher_analytics_without_mastery_score")
            self.assertNotIn("masteryScore", data)

    def test_student_and_standalone_system_admin_cannot_use_teacher_analytics(self):
        users = [
            {"username": "student1", "role": "student", "roles": ["student"], "preferredGroup": "grpBio"},
            {"username": "sys1", "role": "system_admin", "roles": ["system_admin"], "preferredGroup": "grpBio"},
        ]
        for user in users:
            with self.subTest(role=user["role"]), self.assertRaises(ApiError) as caught:
                analytics.build_teacher_analytics(user)
            self.assertEqual(caught.exception.status, 403)

    def test_teacher_analytics_requires_login(self):
        with self.assertRaises(ApiError) as caught:
            analytics.build_teacher_analytics(None)
        self.assertEqual(caught.exception.status, 401)

    def test_teacher_analytics_route_is_get_only_and_session_scoped(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")
        user = {"username": "teacher1", "role": "clinical_teacher", "roles": ["clinical_teacher"], "preferredGroup": "grpBio"}
        owner = SimpleNamespace(app=app, _current_user=lambda: user)
        register_training_command_center(owner)
        client = app.test_client()
        expected = {
            "scope": {"kind": "assigned"}, "summary": {}, "learners": [], "timeline": [],
            "source": "scoped-learning-exam-pgy-records",
        }
        with patch.object(analytics, "build_teacher_analytics", return_value=expected) as build:
            response = client.get("/api/training-command-center/teacher-analytics")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), expected)
        build.assert_called_once_with(user)
        self.assertEqual(client.post("/api/training-command-center/teacher-analytics").status_code, 405)


if __name__ == "__main__":
    unittest.main()
