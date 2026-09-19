import unittest
from unittest.mock import patch

from teacher_app.common.errors import ApiError
from teacher_app.exams import repository as repo
from teacher_app.exams import service
from tests.exam_support import ExamBase, submit_payload


class ExamServiceTests(unittest.TestCase):
    def setUp(self):
        self.base = ExamBase()
        repo.init_schema(self.base)
        category_patch = patch.object(
            service.assessment_repository,
            "get_category_full",
            side_effect=self.base.get_quiz_category,
        )
        questions_patch = patch.object(
            service.assessment_repository,
            "list_questions",
            side_effect=lambda category_id, include_inactive=False: [
                dict(question)
                for question in self.base.list_quiz_questions(category_id)
                if include_inactive or question.get("active", True)
            ],
        )
        category_patch.start()
        questions_patch.start()
        self.addCleanup(category_patch.stop)
        self.addCleanup(questions_patch.stop)

    def tearDown(self):
        self.base.close()

    def _start(self):
        return service.start_attempt(self.base, self.base.user, {"quizCategoryId": "quiz1"})

    def _counts(self):
        conn, _ = self.base._db_conn()
        try:
            attempt = conn.execute("SELECT status FROM exam_attempts").fetchone()[0]
            records = conn.execute("SELECT COUNT(*) FROM exam_records").fetchone()[0]
            review = conn.execute("SELECT review_status FROM exam_records").fetchone()
            return attempt, records, review[0] if review else None
        finally:
            conn.close()

    def test_start_and_resume_never_leak_answer_keys(self):
        started = self._start()
        resumed = service.resume_attempt(self.base, self.base.user, started["attemptId"])
        for response in (started, resumed):
            serialized = str(response["questions"])
            self.assertNotIn("correct", serialized)
            self.assertNotIn("acceptedAnswers", serialized)
            self.assertNotIn("explanation", serialized)

    def test_server_grading_ignores_client_score(self):
        started = self._start()
        payload = submit_payload([0, "essay response"])
        payload.update({"score": 100, "status": "合格", "correctCount": 99})
        result = service.submit_attempt(self.base, self.base.user, started["attemptId"], payload)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["correctCount"], 0)
        self.assertEqual(result["status"], "待人工批改")

    def test_evaluator_identity_is_snapshotted_from_reviewed_category(self):
        self.base.category.update({"reviewerName": "審核教師", "reviewerTitle": "資深醫檢師"})
        started = self._start()
        self.assertEqual(started["evaluatorName"], "審核教師")
        self.assertEqual(started["evaluatorTitle"], "資深醫檢師")
        payload = {"answers": [1, "essay response"], "evaluatorName": "Browser Fake", "evaluatorTitle": "Browser Fake"}
        service.submit_attempt(self.base, self.base.user, started["attemptId"], payload)
        conn, _ = self.base._db_conn()
        try:
            row = conn.execute("SELECT evaluator_name,evaluator_title FROM exam_records").fetchone()
        finally:
            conn.close()
        self.assertEqual(tuple(row), ("審核教師", "資深醫檢師"))

    def test_submission_records_item_analytics_without_trusting_timing_for_score(self):
        conn, _ = self.base._db_conn()
        try:
            conn.execute("""
                CREATE TABLE question_attempt_analytics (
                    question_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    selected_option TEXT NOT NULL DEFAULT '',
                    is_correct INTEGER NOT NULL DEFAULT 0,
                    attempt_score REAL NOT NULL DEFAULT 0,
                    response_seconds REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(question_id, attempt_id)
                )
            """)
        finally:
            conn.close()
        started = self._start()
        answers = [
            1 if question.get("id") == "q1" else "essay response"
            for question in started["questions"]
        ]
        timings = [
            12.5 if question.get("id") == "q1" else 999999
            for question in started["questions"]
        ]
        result = service.submit_attempt(
            self.base,
            self.base.user,
            started["attemptId"],
            {"answers": answers, "responseTimings": timings},
        )
        self.assertEqual(result["score"], 50)
        conn, _ = self.base._db_conn()
        try:
            rows = conn.execute(
                "SELECT question_id,selected_option,is_correct,attempt_score,response_seconds "
                "FROM question_attempt_analytics ORDER BY question_id"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["question_id"], "q1")
        self.assertEqual(rows[0]["selected_option"], "1")
        self.assertEqual(rows[0]["is_correct"], 1)
        self.assertEqual(rows[0]["attempt_score"], 50.0)
        self.assertEqual(rows[0]["response_seconds"], 12.5)

    def test_essay_submission_is_pending_human_review(self):
        started = self._start()
        result = service.submit_attempt(self.base, self.base.user, started["attemptId"], submit_payload())
        self.assertEqual(result["essayCount"], 1)
        self.assertEqual(self._counts(), ("submitted", 1, "pending"))

    def test_double_submit_creates_one_record(self):
        started = self._start()
        service.submit_attempt(self.base, self.base.user, started["attemptId"], submit_payload())
        with self.assertRaises(ApiError) as duplicate:
            service.submit_attempt(self.base, self.base.user, started["attemptId"], submit_payload())
        self.assertEqual(duplicate.exception.status, 409)
        self.assertEqual(duplicate.exception.message, "此考核已經提交，不能重複計分。")
        self.assertEqual(self._counts(), ("submitted", 1, "pending"))

    def test_record_failure_rolls_back_attempt(self):
        started = self._start()
        with patch.object(repo, "insert_exam_record", side_effect=RuntimeError("database unavailable")):
            with self.assertRaises(RuntimeError):
                service.submit_attempt(self.base, self.base.user, started["attemptId"], submit_payload())
        self.assertEqual(self._counts(), ("started", 0, None))


if __name__ == "__main__":
    unittest.main()
