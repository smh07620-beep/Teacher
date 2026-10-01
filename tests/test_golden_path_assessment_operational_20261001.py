import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from teacher_app.exams import records
from teacher_app.exams import repository as repo
from teacher_app.exams import service
from tests.exam_support import ExamBase


class AssessmentGoldenPathOperationalTests(unittest.TestCase):
    """GP-04: learner submission must become a server-attributed reviewed result."""

    def setUp(self):
        self.base = ExamBase()
        repo.init_schema(self.base)
        conn, _ = self.base._db_conn()
        try:
            conn.execute("ALTER TABLE exam_records ADD COLUMN reviewed_at TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE exam_records ADD COLUMN reviewer_name TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE exam_records ADD COLUMN review_comment TEXT NOT NULL DEFAULT ''")
        finally:
            conn.close()

        self.base.category.update({
            "reviewerName": "考卷設定教師",
            "reviewerTitle": "醫檢師",
        })
        self.category_patch = patch.object(
            service.assessment_repository,
            "get_category_full",
            side_effect=self.base.get_quiz_category,
        )
        self.questions_patch = patch.object(
            service.assessment_repository,
            "list_questions",
            side_effect=lambda category_id, include_inactive=False: [
                dict(question)
                for question in self.base.list_quiz_questions(category_id)
                if include_inactive or question.get("active", True)
            ],
        )
        self.shuffle_patch = patch.object(service.random, "shuffle", side_effect=lambda items: None)
        self.transaction_patch = patch.object(
            records.common_db,
            "transaction",
            side_effect=lambda: self._transaction(),
        )
        for active_patch in (
            self.category_patch,
            self.questions_patch,
            self.shuffle_patch,
            self.transaction_patch,
        ):
            active_patch.start()
            self.addCleanup(active_patch.stop)

    def tearDown(self):
        self.base.close()

    @contextmanager
    def _transaction(self):
        conn, kind = self.base._db_conn()
        try:
            conn.execute("BEGIN")
            yield conn, kind
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def test_submit_review_and_result_use_server_authoritative_identity(self):
        started = service.start_attempt(
            self.base,
            self.base.user,
            {"quizCategoryId": "quiz1"},
        )
        self.assertEqual(started["evaluatorName"], "考卷設定教師")
        self.assertEqual(started["evaluatorTitle"], "醫檢師")

        submitted = service.submit_attempt(
            self.base,
            self.base.user,
            started["attemptId"],
            {
                "answers": [1, "申論作答"],
                "evaluatorName": "Browser Fake Evaluator",
                "evaluatorTitle": "Browser Fake Title",
                "examineeRole": "student",
            },
        )
        self.assertEqual(submitted["status"], "待人工批改")

        reviewer_user = {
            "username": "teacher1",
            "name": "王老師",
            "title": "資深醫檢師",
            "role": "clinical_teacher",
        }
        reviewed = records.review_record(
            submitted["recordId"],
            {
                "essayScores": {"1": 100},
                "essayComments": {"1": "內容完整"},
                "reviewComment": "完成人工批改",
                "reviewerName": "Browser Fake Reviewer",
            },
            reviewer_user=reviewer_user,
        )
        self.assertTrue(reviewed["ok"])
        self.assertEqual(reviewed["score"], 100)
        self.assertEqual(reviewed["status"], "合格")
        self.assertEqual(reviewed["reviewerName"], "王老師")
        self.assertEqual(reviewed["reviewerTitle"], "資深醫檢師")

        conn, _ = self.base._db_conn()
        try:
            row = conn.execute(
                "SELECT review_status,reviewer_name,evaluator_name,evaluator_title,answers_detail "
                "FROM exam_records WHERE id=?",
                (submitted["recordId"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row["review_status"], "completed")
        self.assertEqual(row["reviewer_name"], "王老師")
        self.assertEqual(row["evaluator_name"], "考卷設定教師")
        self.assertEqual(row["evaluator_title"], "醫檢師")
        answers = json.loads(row["answers_detail"])
        essay = next(answer for answer in answers if answer.get("questionType") == "essay")
        self.assertEqual(essay["reviewerName"], "王老師")
        self.assertEqual(essay["reviewerTitle"], "資深醫檢師")
        self.assertNotEqual(essay["reviewerName"], "Browser Fake Reviewer")

    def test_manual_review_requires_authenticated_reviewer_identity(self):
        started = service.start_attempt(self.base, self.base.user, {"quizCategoryId": "quiz1"})
        submitted = service.submit_attempt(
            self.base,
            self.base.user,
            started["attemptId"],
            {"answers": [1, "申論作答"], "examineeRole": "student"},
        )
        with self.assertRaises(records.RecordError) as denied:
            records.review_record(
                submitted["recordId"],
                {"essayScores": {"1": 100}, "reviewerName": "Browser Fake Reviewer"},
                reviewer_user=None,
            )
        self.assertEqual(denied.exception.status, 401)


if __name__ == "__main__":
    unittest.main()
