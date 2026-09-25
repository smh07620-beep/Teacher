import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from teacher_app.command_center import dashboard_service
from teacher_app.learning import access as learning_access
from teacher_app.learning import progress_service
from teacher_app.learning.routes import register_smart_learning


BIO_USER = {
    "username": "student.bio",
    "name": "Bio Student",
    "empId": "E100",
    "role": "student",
    "preferredArea": "internal",
    "preferredGroup": "grpBio",
}


class LearningScopeAccessTests(unittest.TestCase):
    def test_student_access_is_limited_to_preferred_area_and_group(self):
        self.assertTrue(
            learning_access.can_access_learning_item(
                BIO_USER,
                {"area": "internal", "group": "grpBio"},
            )
        )
        self.assertFalse(
            learning_access.can_access_learning_item(
                BIO_USER,
                {"area": "internal", "group": "grpMicro"},
            )
        )
        self.assertFalse(
            learning_access.can_access_learning_item(
                BIO_USER,
                {"area": "pgy", "group": "grpBio"},
            )
        )

    def test_education_admin_can_inspect_cross_group_learning_content(self):
        admin = {
            **BIO_USER,
            "username": "edu.admin",
            "role": "education_admin",
        }
        self.assertTrue(
            learning_access.can_access_learning_item(
                admin,
                {"area": "pgy", "group": "grpMicro"},
            )
        )


class LegacyProgressScopeTests(unittest.TestCase):
    def test_my_progress_rejects_cross_group_query(self):
        with self.assertRaises(progress_service.ProgressError) as caught:
            progress_service.my_progress(
                BIO_USER,
                area="internal",
                group="grpMicro",
            )
        self.assertEqual(caught.exception.status, 403)

    @patch("teacher_app.learning.progress_service.material_repository.get_material")
    def test_manual_completion_rejects_cross_group_material(self, get_material):
        get_material.return_value = {
            "id": "mat-micro",
            "active": True,
            "area": "internal",
            "group": "grpMicro",
        }
        with self.assertRaises(progress_service.ProgressError) as caught:
            progress_service.mark_material_complete(BIO_USER, "mat-micro")
        self.assertEqual(caught.exception.status, 403)


class DashboardScopeTests(unittest.TestCase):
    def test_dashboard_excludes_other_groups_from_totals_and_passed_counts(self):
        class FakeConnection:
            def execute(self, sql, params=()):
                if "FROM material_progress" in sql:
                    return SimpleNamespace(fetchall=lambda: [
                        {"material_id": "mat-bio", "name": "Bio Student", "completed_at": "2026-09-25T00:00:00+00:00"},
                        {"material_id": "mat-micro", "name": "Bio Student", "completed_at": "2026-09-25T00:00:00+00:00"},
                    ])
                if "FROM exam_records" in sql:
                    return SimpleNamespace(fetchall=lambda: [
                        {
                            "id": "r-bio",
                            "emp_id": "E100",
                            "quiz_category_id": "quiz-bio",
                            "course_id": "course-bio",
                            "training_area": "internal",
                            "group_key": "grpBio",
                            "score": 100,
                            "passing_score": 80,
                            "review_status": "completed",
                            "created_at": "2026-09-25T10:00:00+00:00",
                        },
                        {
                            "id": "r-micro",
                            "emp_id": "E100",
                            "quiz_category_id": "quiz-micro",
                            "course_id": "course-micro",
                            "training_area": "internal",
                            "group_key": "grpMicro",
                            "score": 100,
                            "passing_score": 80,
                            "review_status": "completed",
                            "created_at": "2026-09-25T11:00:00+00:00",
                        },
                    ])
                if "FROM pgy_assessments" in sql:
                    return SimpleNamespace(fetchall=lambda: [])
                raise AssertionError(sql)

        @contextmanager
        def fake_read_connection():
            yield FakeConnection(), "sqlite"

        materials = [
            {"id": "mat-bio", "active": True, "area": "internal", "group": "grpBio", "courseId": "course-bio"},
            {"id": "mat-micro", "active": True, "area": "internal", "group": "grpMicro", "courseId": "course-micro"},
        ]
        quizzes = [
            {"id": "quiz-bio", "active": True, "area": "internal", "group": "grpBio", "courseId": "course-bio", "passingScore": 80},
            {"id": "quiz-micro", "active": True, "area": "internal", "group": "grpMicro", "courseId": "course-micro", "passingScore": 80},
        ]
        courses = [
            {"id": "course-bio", "area": "internal", "group": "grpBio", "startDate": "", "endDate": ""},
            {"id": "course-micro", "area": "internal", "group": "grpMicro", "startDate": "", "endDate": ""},
        ]

        with patch("teacher_app.command_center.dashboard_service.common_db.read_connection", fake_read_connection), \
             patch("teacher_app.command_center.dashboard_service.material_repository.list_uploaded_materials", return_value=materials), \
             patch("teacher_app.command_center.dashboard_service.assessment_repository.list_categories", return_value=quizzes), \
             patch("teacher_app.command_center.dashboard_service.course_repository.list_courses", return_value=courses):
            summary = dashboard_service.dashboard_summary(BIO_USER, today="2026-09-25")

        self.assertEqual(summary["scope"], {"area": "internal", "group": "grpBio"})
        self.assertEqual(summary["activeCourses"], 1)
        self.assertEqual(summary["materialsTotal"], 1)
        self.assertEqual(summary["materialsCompleted"], 1)
        self.assertEqual(summary["examsTotal"], 1)
        self.assertEqual(summary["examsPassed"], 1)
        self.assertEqual(summary["progressPercent"], 100)
        self.assertEqual(summary["latestExam"]["groupKey"], "grpBio")


class SmartLearningRouteScopeTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.owner = SimpleNamespace(
            app=self.app,
            _current_user=lambda: dict(BIO_USER),
        )
        paths = SimpleNamespace(uploaded_slides_dir=".")
        register_smart_learning(
            self.owner,
            paths=paths,
            material_getter=lambda _material_id: {
                "id": "mat-micro",
                "active": True,
                "area": "internal",
                "group": "grpMicro",
                "storageBackend": "local",
            },
        )
        self.client = self.app.test_client()

    def test_learning_progress_get_hides_cross_group_material(self):
        response = self.client.get("/api/learning-progress/mat-micro")
        self.assertEqual(response.status_code, 404)

    def test_learning_progress_put_hides_cross_group_material(self):
        response = self.client.put(
            "/api/learning-progress/mat-micro",
            json={"position": {"page": 1}, "progress": 50},
        )
        self.assertEqual(response.status_code, 404)

    def test_material_search_hides_cross_group_material(self):
        response = self.client.get("/api/material-search?materialId=mat-micro&q=cbc")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])


if __name__ == "__main__":
    unittest.main()
