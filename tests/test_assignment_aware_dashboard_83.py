import datetime as dt
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from teacher_app.command_center import dashboard_service


USER = {
    "username": "student.bio",
    "name": "Bio Student",
    "empId": "E100",
    "role": "student",
    "preferredArea": "internal",
    "preferredGroup": "grpBio",
}


class AssignmentAwareDashboardTests(unittest.TestCase):
    def _summary(self, assignments):
        class FakeConnection:
            def execute(self, sql, params=()):
                if "FROM material_progress" in sql:
                    return SimpleNamespace(fetchall=lambda: [
                        {"material_id": "m-required", "name": "Bio Student", "completed_at": "2026-09-24T00:00:00+00:00"},
                        {"material_id": "m-optional", "name": "Bio Student", "completed_at": "2026-09-24T00:00:00+00:00"},
                    ])
                if "FROM exam_records" in sql:
                    return SimpleNamespace(fetchall=lambda: [])
                if "FROM pgy_assessments" in sql:
                    return SimpleNamespace(fetchall=lambda: [])
                raise AssertionError(sql)

        @contextmanager
        def fake_read_connection():
            yield FakeConnection(), "sqlite"

        materials = [
            {"id": "m-required", "active": True, "area": "internal", "group": "grpBio", "courseId": "c-required"},
            {"id": "m-optional", "active": True, "area": "internal", "group": "grpBio", "courseId": "c-optional"},
            {"id": "m-unassigned", "active": True, "area": "internal", "group": "grpBio", "courseId": "c-unassigned"},
        ]
        quizzes = [
            {"id": "q-required", "active": True, "area": "internal", "group": "grpBio", "courseId": "c-required", "passingScore": 80},
            {"id": "q-optional", "active": True, "area": "internal", "group": "grpBio", "courseId": "c-optional", "passingScore": 80},
            {"id": "q-unassigned", "active": True, "area": "internal", "group": "grpBio", "courseId": "c-unassigned", "passingScore": 80},
        ]
        courses = [
            {"id": "c-required", "title": "必修課", "area": "internal", "group": "grpBio", "startDate": "", "endDate": ""},
            {"id": "c-optional", "title": "選修課", "area": "internal", "group": "grpBio", "startDate": "", "endDate": ""},
            {"id": "c-unassigned", "title": "未指派課", "area": "internal", "group": "grpBio", "startDate": "", "endDate": ""},
        ]
        with patch("teacher_app.command_center.dashboard_service.common_db.read_connection", fake_read_connection), \
             patch("teacher_app.command_center.dashboard_service.material_repository.list_uploaded_materials", return_value=materials), \
             patch("teacher_app.command_center.dashboard_service.assessment_repository.list_categories", return_value=quizzes), \
             patch("teacher_app.command_center.dashboard_service.course_repository.list_courses", return_value=courses), \
             patch("teacher_app.command_center.dashboard_service.assignment_service.list_for_user", return_value=assignments):
            return dashboard_service.dashboard_summary(
                USER,
                today="2026-09-25",
                now=dt.datetime(2026, 9, 25, 12, tzinfo=dt.timezone.utc),
            )

    def test_assignments_switch_dashboard_to_required_course_denominator(self):
        summary = self._summary([
            {
                "id": "a-required", "courseId": "c-required", "required": True,
                "assigneeType": "group", "assigneeKey": "grpBio",
                "dueAt": "2026-09-24T12:00:00+00:00", "assignedAt": "2026-09-01T00:00:00+00:00",
                "assignedBy": "leader", "area": "internal", "group": "grpBio",
            },
            {
                "id": "a-optional", "courseId": "c-optional", "required": False,
                "assigneeType": "user", "assigneeKey": "student.bio",
                "dueAt": "", "assignedAt": "2026-09-02T00:00:00+00:00",
                "assignedBy": "leader", "area": "internal", "group": "grpBio",
            },
        ])
        self.assertTrue(summary["assignmentMode"])
        self.assertEqual(summary["activeCourses"], 2)
        self.assertEqual(summary["materialsTotal"], 1)
        self.assertEqual(summary["materialsCompleted"], 1)
        self.assertEqual(summary["examsTotal"], 1)
        self.assertEqual(summary["examsPassed"], 0)
        self.assertEqual(summary["progressPercent"], 50)
        self.assertEqual([item["courseId"] for item in summary["pendingExams"]], ["c-required"])
        self.assertEqual(summary["assignmentsTotal"], 2)
        self.assertEqual(summary["requiredAssignmentsPending"], 1)
        self.assertEqual(summary["assignmentsOverdue"], 1)

        required = next(item for item in summary["assignments"] if item["courseId"] == "c-required")
        optional = next(item for item in summary["assignments"] if item["courseId"] == "c-optional")
        self.assertFalse(required["completed"])
        self.assertTrue(required["overdue"])
        self.assertFalse(optional["completed"])
        self.assertFalse(optional["overdue"])

    def test_no_assignments_retains_existing_scope_fallback(self):
        summary = self._summary([])
        self.assertFalse(summary["assignmentMode"])
        self.assertEqual(summary["activeCourses"], 3)
        self.assertEqual(summary["materialsTotal"], 3)
        self.assertEqual(summary["materialsCompleted"], 2)
        self.assertEqual(summary["examsTotal"], 3)
        self.assertEqual(summary["assignments"], [])


if __name__ == "__main__":
    unittest.main()
