import datetime as dt
import unittest
from unittest.mock import patch

from teacher_app.command_center import course_tracking


def _run(due, exam_rows, now):
    user = {"username": "admin", "role": "education_admin", "roles": ["education_admin"], "permissions": ["learning.assign"]}
    assignment = {"courseId": "c1", "area": "internal", "group": "grpBio", "assigneeType": "user", "assigneeKey": "s1", "dueAt": due, "active": True}
    course = {"id": "c1", "title": "檢驗流程一致性", "area": "internal", "group": "grpBio", "active": True, "lifecycleStatus": "published"}
    learner = {"username": "s1", "name": "Learner", "empId": "E1", "area": "internal", "group": "grpBio", "active": True}
    materials = [{"id": f"m{i}", "courseId": "c1", "active": True, "version": 1, "requiredCompletionVersion": 1} for i in (1, 2)]
    exam = {"id": "q1", "courseId": "c1", "active": True}
    with patch.object(course_tracking.assignment_service, "admin_list", return_value=[assignment]), \
         patch.object(course_tracking, "_account_rows", return_value=[learner]), \
         patch.object(course_tracking.course_repository, "get_course", return_value=course), \
         patch.object(course_tracking.material_repository, "list_uploaded_materials", return_value=materials), \
         patch.object(course_tracking.assessment_repository, "list_categories", return_value=[exam]), \
         patch.object(course_tracking, "_progress_rows", return_value=[]), \
         patch.object(course_tracking, "_legacy_progress_rows", return_value=[]), \
         patch.object(course_tracking, "_exam_rows", return_value=exam_rows), \
         patch.object(course_tracking, "has_permission", return_value=True):
        return course_tracking.build_course_tracking(user, now=now)["courses"][0]["learners"][0]


PASSED = [{"emp_id": "E1", "course_id": "c1", "quiz_category_id": "q1", "score": 100, "passing_score": 80, "review_status": "completed"}]
TPE = dt.timezone(dt.timedelta(hours=8))


class OverdueRule1106Tests(unittest.TestCase):
    def test_passed_exam_is_not_overdue_even_if_materials_unread(self):
        row = _run("2026-11-01", PASSED, dt.datetime(2026, 11, 6, 14, 0, tzinfo=TPE))
        self.assertTrue(row["examPassed"])
        self.assertEqual(row["materialsCompleted"], 0)
        self.assertFalse(row["overdue"])

    def test_date_only_deadline_lasts_the_whole_day(self):
        self.assertFalse(_run("2026-11-06", [], dt.datetime(2026, 11, 6, 23, 59, tzinfo=TPE))["overdue"])
        self.assertTrue(_run("2026-11-06", [], dt.datetime(2026, 11, 7, 0, 0, tzinfo=TPE))["overdue"])

    def test_not_passed_after_deadline_is_overdue(self):
        self.assertTrue(_run("2026-11-01", [], dt.datetime(2026, 11, 6, 14, 0, tzinfo=TPE))["overdue"])


if __name__ == "__main__":
    unittest.main()
