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
