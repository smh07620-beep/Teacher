import contextlib
import sqlite3
import unittest
from unittest.mock import patch

import release_contract
import schema_migrations
from teacher_app.common import db as common_db
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.learning import feedback_service
from teacher_app.maintenance.course_feedback_migration import course_feedback_87


class CourseFeedback87Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        course_feedback_87(self.conn, "sqlite")
        self.course = {"id": "course-1", "title": "輸血安全課程", "active": True, "area": "internal", "group": "grpBB"}
        self.student = {"username": "student.a", "role": "student", "roles": ["student"], "preferredArea": "internal", "preferredGroup": "grpBB"}
        self.student_b = {**self.student, "username": "student.b"}
        self.admin = {"username": "admin.a", "role": "system_admin", "roles": ["system_admin"], "preferredArea": "internal", "preferredGroup": "grpBio"}

    def tearDown(self):
        self.conn.close()

    @contextlib.contextmanager
    def _read(self):
        yield self.conn, "sqlite"

    @contextlib.contextmanager
    def _tx(self):
        try:
            yield self.conn, "sqlite"
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _patches(self):
        return (
            patch.object(common_db, "read_connection", self._read),
            patch.object(common_db, "transaction", self._tx),
            patch.object(course_repository, "get_course", side_effect=lambda course_id: self.course if course_id == "course-1" else None),
        )

    def test_release_contract_registers_0087_once_after_0086(self):
        versions = [version for version, _fn in schema_migrations.MIGRATIONS]
        self.assertEqual(versions.count("0087-course-feedback"), 1)
        self.assertLess(release_contract.REQUIRED_MIGRATIONS.index("0086-notification-read-state"), release_contract.REQUIRED_MIGRATIONS.index("0087-course-feedback"))
        self.assertLess(release_contract.REQUIRED_MIGRATIONS.index("0087-course-feedback"), release_contract.REQUIRED_MIGRATIONS.index("0088-saved-learning-items"))

    def test_student_can_create_and_update_only_own_feedback(self):
        patches = self._patches()
        with patches[0], patches[1], patches[2]:
            first = feedback_service.submit_feedback(self.student, "course-1", {"rating": 4, "comment": "內容實用"})
            second = feedback_service.submit_feedback(self.student, "course-1", {"rating": 5, "comment": "更新後更清楚"})
            own = feedback_service.get_own_feedback(self.student, "course-1")
        self.assertTrue(first["ok"])
        self.assertEqual(second["feedback"]["rating"], 5)
        self.assertEqual(own["feedback"]["comment"], "更新後更清楚")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM course_feedback").fetchone()[0], 1)

    def test_feedback_is_isolated_per_user(self):
        patches = self._patches()
        with patches[0], patches[1], patches[2]:
            feedback_service.submit_feedback(self.student, "course-1", {"rating": 5, "comment": "A"})
            feedback_service.submit_feedback(self.student_b, "course-1", {"rating": 3, "comment": "B"})
            own_a = feedback_service.get_own_feedback(self.student, "course-1")
            own_b = feedback_service.get_own_feedback(self.student_b, "course-1")
        self.assertEqual(own_a["feedback"]["comment"], "A")
        self.assertEqual(own_b["feedback"]["comment"], "B")

    def test_invalid_rating_and_cross_scope_fail_closed(self):
        patches = self._patches()
        with patches[0], patches[1], patches[2]:
            with self.assertRaises(ApiError) as invalid:
                feedback_service.submit_feedback(self.student, "course-1", {"rating": 6})
            self.assertEqual(invalid.exception.code, "INVALID_COURSE_FEEDBACK_RATING")
            other_scope = {**self.student, "preferredGroup": "grpHema"}
            with self.assertRaises(ApiError) as hidden:
                feedback_service.get_own_feedback(other_scope, "course-1")
            self.assertEqual(hidden.exception.status, 404)

    def test_summary_is_manager_only_and_contains_no_identity_or_comments(self):
        patches = self._patches()
        with patches[0], patches[1], patches[2]:
            feedback_service.submit_feedback(self.student, "course-1", {"rating": 5, "comment": "A"})
            feedback_service.submit_feedback(self.student_b, "course-1", {"rating": 3, "comment": "B"})
            with self.assertRaises(ApiError) as forbidden:
                feedback_service.feedback_summary(self.student, "course-1")
            self.assertEqual(forbidden.exception.status, 403)
            summary = feedback_service.feedback_summary(self.admin, "course-1")
        self.assertEqual(summary["responseCount"], 2)
        self.assertEqual(summary["averageRating"], 4.0)
        self.assertEqual(summary["ratingCounts"]["5"], 1)
        self.assertEqual(summary["ratingCounts"]["3"], 1)
        self.assertNotIn("username", summary)
        self.assertNotIn("comment", summary)


if __name__ == "__main__":
    unittest.main()
