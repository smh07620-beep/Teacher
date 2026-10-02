import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from teacher_app.command_center import competency
from teacher_app.command_center.routes import register_training_command_center
from teacher_app.common.errors import ApiError


class TeacherCompetencyP2Tests(unittest.TestCase):
    def test_teacher_scoped_roles_reuse_canonical_competency_projection(self):
        expected = {
            "scope": {"kind": "assigned"},
            "learners": [],
            "summary": {},
            "assessmentTypes": [],
        }
        users = [
            {
                "username": "teacher1",
                "role": "clinical_teacher",
                "roles": ["clinical_teacher"],
                "preferredGroup": "grpBio",
            },
            {
                "username": "leader1",
                "role": "group_leader",
                "roles": ["group_leader"],
                "preferredGroup": "grpBio",
            },
            {
                "username": "edu1",
                "role": "education_admin",
                "roles": ["education_admin"],
                "preferredGroup": "grpBio",
            },
        ]
        for user in users:
            with self.subTest(role=user["role"]), patch.object(
                competency, "build_competency_matrix", return_value=dict(expected)
            ) as build:
                data = competency.build_teacher_competency_matrix(user)
            build.assert_called_once_with(user, now=None)
            self.assertEqual(data["source"], "formal-pgy-assessments")
            self.assertEqual(
                data["interpretation"],
                "formal_assessment_tracking_without_mastery_score",
            )

    def test_student_and_standalone_system_admin_cannot_use_teacher_competency(self):
        users = [
            {
                "username": "student1",
                "role": "student",
                "roles": ["student"],
                "preferredGroup": "grpBio",
            },
            {
                "username": "sys1",
                "role": "system_admin",
                "roles": ["system_admin"],
                "preferredGroup": "grpBio",
            },
        ]
        for user in users:
            with self.subTest(role=user["role"]), self.assertRaises(ApiError) as caught:
                competency.build_teacher_competency_matrix(user)
            self.assertEqual(caught.exception.status, 403)

    def test_teacher_competency_route_is_get_only_and_session_scoped(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")
        user = {
            "username": "teacher1",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredGroup": "grpBio",
        }
        owner = SimpleNamespace(app=app, _current_user=lambda: user)
        register_training_command_center(owner)
        client = app.test_client()
        expected = {
            "scope": {"kind": "assigned"},
            "learners": [],
            "summary": {},
            "assessmentTypes": [],
            "source": "formal-pgy-assessments",
        }
        with patch.object(
            competency, "build_teacher_competency_matrix", return_value=expected
        ) as build:
            response = client.get("/api/training-command-center/teacher-competency")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), expected)
        build.assert_called_once_with(user)
        self.assertEqual(
            client.post("/api/training-command-center/teacher-competency").status_code,
            405,
        )


if __name__ == "__main__":
    unittest.main()
