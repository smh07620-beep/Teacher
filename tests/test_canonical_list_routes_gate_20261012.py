"""The production app (create_app) must gate /api/courses and /api/quiz-categories itself.

The legacy-host routes were gated, but create_app serves the canonical routes, so
an unassigned student still saw the course and its exam in the learner list.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

COURSE = {"id": "c1", "area": "internal", "group": "grpBio", "title": "Sebia", "active": True, "lifecycleStatus": "published"}
OTHER = {"id": "c2", "area": "internal", "group": "grpBio", "title": "Other", "active": True, "lifecycleStatus": "published"}
EXAMS = [
    {"id": "e1", "title": "Sebia exam", "courseId": "c1", "area": "internal", "group": "grpBio"},
    {"id": "e2", "title": "Other exam", "courseId": "c2", "area": "internal", "group": "grpBio"},
    {"id": "e3", "title": "Loose exam", "courseId": "", "area": "internal", "group": "grpBio"},
]


class CanonicalListGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        cls._env = {
            "TEACHER_SQLITE_PATH": cls._tmp + "/t.db",
            "MATERIAL_STORAGE": cls._tmp + "/m",
            "SECRET_KEY": "x" * 40,
            "PRODUCTION_REQUIRE_SECRET": "false",
            "SESSION_COOKIE_SECURE": "false",
            "CSRF_ORIGIN_CHECK": "false",
            "MATERIAL_BACKGROUND_JOBS": "false",
            "MATERIAL_WORKER_ENABLED": "false",
        }
        cls._old = {k: os.environ.get(k) for k in list(cls._env) + ["DATABASE_URL"]}
        os.environ.pop("DATABASE_URL", None)
        os.environ.update(cls._env)
        from teacher_app import create_app
        from teacher_app.auth import accounts

        cls.app = create_app()
        accounts.create_account({
            "username": "gate_student", "password": "Passw0rd!x1", "name": "學員", "empId": "G001",
            "role": "student", "roles": ["student"], "preferredArea": "internal", "preferredGroup": "grpBio",
        })

    @classmethod
    def tearDownClass(cls):
        for key, value in cls._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _client(self):
        client = self.app.test_client()
        response = client.post("/api/auth/login", json={"username": "gate_student", "password": "Passw0rd!x1"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return client

    def _get(self, path, assigned):
        rows = [{"courseId": course_id} for course_id in assigned]
        with patch("teacher_app.courses.service.list_courses", return_value=[COURSE, OTHER]), \
             patch("teacher_app.assessments.service.list_categories", return_value=[dict(e) for e in EXAMS]), \
             patch("teacher_app.learning.assignment_repository.list_for_user", return_value=rows), \
             patch("teacher_app.learning.assignment_repository.list_personal_course_ids", return_value=[]):
            return self._client().get(path)

    def test_unassigned_student_sees_no_course_or_course_exam(self):
        courses = self._get("/api/courses?area=internal&group=grpBio&view=learner", []).get_json()
        self.assertEqual([c["id"] for c in courses], [])
        exams = self._get("/api/quiz-categories?area=internal&group=grpBio&view=learner", []).get_json()
        self.assertEqual([e["id"] for e in exams], ["e3"])

    def test_assigned_student_sees_only_the_assigned_course_and_its_exam(self):
        with patch("teacher_app.courses.visibility._default_materials", return_value=[]):
            courses = self._get("/api/courses?area=internal&group=grpBio&view=learner", ["c1"]).get_json()
        self.assertEqual([c["id"] for c in courses], ["c1"])
        exams = self._get("/api/quiz-categories?area=internal&group=grpBio&view=learner", ["c1"]).get_json()
        self.assertEqual(sorted(e["id"] for e in exams), ["e1", "e3"])

    def test_student_is_gated_even_without_the_view_flag(self):
        exams = self._get("/api/quiz-categories?area=internal&group=grpBio", []).get_json()
        self.assertEqual([e["id"] for e in exams], ["e3"])


if __name__ == "__main__":
    unittest.main()
