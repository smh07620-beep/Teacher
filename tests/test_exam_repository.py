import unittest

from teacher_app.exams import repository as repo
from tests.exam_support import ExamBase


class ExamRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.base = ExamBase()
        repo.init_schema(self.base)
        self.attempt = {
            "id": "a1", "username": "student1", "emp_id": "S001", "quiz_category_id": "quiz1",
            "quiz_title": "Quiz", "group_key": "grpBio", "training_area": "internal", "course_id": "",
            "passing_score": 80, "publication_id": "", "publication_hash": "", "questions_json": "[]",
            "status": "started", "record_id": "", "started_at": "2026-09-09T00:00:00+00:00", "submitted_at": "",
        }
        with repo.transaction(self.base) as (conn, kind):
            repo.create_attempt(conn, kind, self.attempt)

    def tearDown(self):
        self.base.close()

    def test_conditional_submit_allows_only_one_update(self):
        with repo.transaction(self.base) as (conn, kind):
            repo.mark_submitted(conn, kind, "a1", "r1", "now")
        with self.assertRaises(repo.AttemptConflict):
            with repo.transaction(self.base) as (conn, kind):
                repo.mark_submitted(conn, kind, "a1", "r2", "later")
        conn, kind = self.base._db_conn()
        try:
            attempt = repo.get_attempt(conn, kind, "a1")
        finally:
            conn.close()
        self.assertEqual(attempt["record_id"], "r1")

    def test_transaction_rolls_back_state_change(self):
        with self.assertRaises(RuntimeError):
            with repo.transaction(self.base) as (conn, kind):
                repo.mark_submitted(conn, kind, "a1", "r1", "now")
                raise RuntimeError("record insert failed")
        conn, kind = self.base._db_conn()
        try:
            attempt = repo.get_attempt(conn, kind, "a1")
        finally:
            conn.close()
        self.assertEqual(attempt["status"], "started")


if __name__ == "__main__":
    unittest.main()
