import datetime as dt
import unittest
from unittest.mock import patch

from teacher_app.command_center import dashboard_service
from teacher_app.command_center import service as command_center_service
from teacher_app.courses import repository as course_repository
from teacher_app.learning import access as learning_access
from teacher_app.learning import calendar_service


class LearningCalendar89Tests(unittest.TestCase):
    def setUp(self):
        self.user = {"username": "student.a", "empId": "E001", "name": "Student A", "role": "student", "roles": ["student"], "preferredArea": "internal", "preferredGroup": "grpBB"}
        self.now = dt.datetime(2026, 9, 26, 0, 0, tzinfo=dt.timezone.utc)

    def test_calendar_aggregates_assignment_course_and_pgy_dates(self):
        dashboard = {"pendingCourses": [{"id": "course-1", "assignmentId": "a1", "title": "輸血安全", "area": "internal", "group": "grpBB", "dueAt": "2026-09-25T12:00:00+00:00", "overdue": True}]}
        courses = [{"id": "course-1", "title": "輸血安全", "active": True, "area": "internal", "group": "grpBB", "startDate": "2026-09-27", "endDate": "2026-10-05"}, {"id": "course-x", "title": "其他組課程", "active": True, "area": "internal", "group": "grpHema", "startDate": "2026-09-27", "endDate": ""}]
        command = {"items": [{"id": "p1", "domain": "pgy", "title": "臨床實務", "group": "grpBB", "dueAt": "2026-09-28T08:00:00+00:00", "overdue": False}]}
        with patch.object(dashboard_service, "dashboard_summary", return_value=dashboard), patch.object(course_repository, "list_courses", return_value=courses), patch.object(learning_access, "can_access_learning_item", side_effect=lambda _user, item: item.get("group") == "grpBB"), patch.object(command_center_service, "build_summary", return_value=command):
            result = calendar_service.calendar_summary(self.user, days=30, now=self.now)
        self.assertEqual([item["kind"] for item in result["events"]], ["course_due", "course_start", "pgy_due", "course_end"])
        self.assertEqual(result["counts"]["overdue"], 1)
        self.assertEqual(result["counts"]["upcoming"], 3)
        self.assertNotIn("course-x", {item.get("courseId") for item in result["events"]})

    def test_range_is_bounded_and_invalid_dates_are_ignored(self):
        courses = [{"id": "c1", "title": "課程", "active": True, "area": "internal", "group": "grpBB", "startDate": "not-a-date", "endDate": "2027-12-01"}]
        with patch.object(dashboard_service, "dashboard_summary", return_value={"pendingCourses": []}), patch.object(course_repository, "list_courses", return_value=courses), patch.object(learning_access, "can_access_learning_item", return_value=True), patch.object(command_center_service, "build_summary", return_value={"items": []}):
            result = calendar_service.calendar_summary(self.user, days=999, now=self.now)
        self.assertEqual(result["windowDays"], 180)
        self.assertEqual(result["events"], [])

    def test_assignment_mode_hides_unassigned_course_dates(self):
        dashboard = {
            "assignmentMode": True,
            "assignments": [{"id": "a1", "courseId": "course-1"}],
            "pendingCourses": [],
        }
        courses = [
            {"id": "course-1", "title": "已指派", "active": True, "area": "internal", "group": "grpBB", "startDate": "2026-09-27", "endDate": ""},
            {"id": "course-2", "title": "未指派", "active": True, "area": "internal", "group": "grpBB", "startDate": "2026-09-28", "endDate": ""},
        ]
        with patch.object(dashboard_service, "dashboard_summary", return_value=dashboard), patch.object(course_repository, "list_courses", return_value=courses), patch.object(learning_access, "can_access_learning_item", return_value=True), patch.object(command_center_service, "build_summary", return_value={"items": []}):
            result = calendar_service.calendar_summary(self.user, days=30, now=self.now)
        self.assertEqual([item["courseId"] for item in result["events"]], ["course-1"])

    def test_past_non_overdue_dates_do_not_crowd_upcoming_calendar(self):
        courses = [{"id": "course-1", "title": "課程", "active": True, "area": "internal", "group": "grpBB", "startDate": "2026-09-20", "endDate": "2026-10-05"}]
        dashboard = {"pendingCourses": [{"id": "course-1", "assignmentId": "a1", "title": "課程", "area": "internal", "group": "grpBB", "dueAt": "2026-09-25T12:00:00+00:00", "overdue": True}]}
        with patch.object(dashboard_service, "dashboard_summary", return_value=dashboard), patch.object(course_repository, "list_courses", return_value=courses), patch.object(learning_access, "can_access_learning_item", return_value=True), patch.object(command_center_service, "build_summary", return_value={"items": []}):
            result = calendar_service.calendar_summary(self.user, days=30, now=self.now)
        self.assertEqual([item["kind"] for item in result["events"]], ["course_due", "course_end"])

    def test_login_is_required(self):
        with self.assertRaises(Exception) as caught:
            calendar_service.calendar_summary(None, now=self.now)
        self.assertEqual(getattr(caught.exception, "status", None), 401)


if __name__ == "__main__": unittest.main()
