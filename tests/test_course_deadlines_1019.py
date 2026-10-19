"""Course cards keep every assigned course's due date, finished or not (2026-10-19)."""
import unittest

from teacher_app.command_center import service


class CourseDeadlineTests(unittest.TestCase):
    def test_finished_courses_keep_their_due_date(self):
        rows = service._course_deadlines({"assignments": [
            {"courseId": "c1", "dueAt": "2026-11-06T23:59:00+08:00", "completed": True},
            {"courseId": "c2", "dueAt": "2026-11-01", "completed": False, "overdue": False},
            {"courseId": "c3", "dueAt": ""},
        ]})
        self.assertEqual([(r["courseId"], r["completed"]) for r in rows], [("c1", True), ("c2", False)])


if __name__ == "__main__":
    unittest.main()
