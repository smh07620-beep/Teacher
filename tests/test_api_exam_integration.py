import unittest
from unittest.mock import patch

from flask import jsonify

from teacher_app.exams import repository as exam_repo
from teacher_app.exams.routes import (
    register_legacy_exam_routes,
)
from tests.exam_support import (
    ExamBase,
    submit_payload,
)


SECRET_KEYS = {
    "correct",
    "correctAnswer",
    "correctAnswers",
    "correctIndices",
    "acceptedAnswers",
    "answer",
    "answers",
    "answerKey",
    "answerKeys",
    "expectedAnswer",
    "expectedAnswers",
    "solution",
    "solutions",
    "explanation",
    "scoringKey",
    "scoringSecret",
    "gradingKey",
    "gradingSecret",
}


def assert_no_answer_secret(
    testcase,
    value,
    path="root",
):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(
                key,
                SECRET_KEYS,
                f"answer-key leakage at {path}.{key}",
            )

            assert_no_answer_secret(
                testcase,
                child,
                f"{path}.{key}",
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_answer_secret(
                testcase,
                child,
                f"{path}[{index}]",
            )


class ExamApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.base = ExamBase()

        self.base.app.config.update(
            TESTING=True,
        )

        # Inject alternate historical answer-key names
        # so recursive sanitization is actually tested.
        self.base.questions[0][
            "correctAnswer"
        ] = "secret"

        self.base.questions[0][
            "answerKey"
        ] = "secret"

        self.base.questions[0][
            "scoringSecret"
        ] = "secret"

        self.base.questions[0][
            "answerConfig"
        ]["answerKey"] = "secret"

        @self.base.app.get(
            "/api/quiz-questions"
        )
        def legacy_questions():
            return jsonify(
                self.base.questions
            )

        register_legacy_exam_routes(
            self.base
        )

        self.client = (
            self.base.app.test_client()
        )

    def tearDown(self):
        self.base.close()

    def start(self):
        response = self.client.post(
            "/api/exam-attempts",
            json={
                "quizCategoryId": "quiz1"
            },
        )

        self.assertEqual(
            response.status_code,
            201,
            response.get_data(
                as_text=True
            ),
        )

        return response.get_json()

    def test_start_attempt_does_not_leak_answer_key(self):
        body = self.start()

        self.assertTrue(
            body["attemptId"]
        )
        self.assertEqual(
            body["status"],
            "started",
        )

        assert_no_answer_secret(
            self,
            body["questions"],
            "start.questions",
        )

    def test_resume_attempt_does_not_leak_answer_key(self):
        started = self.start()

        response = self.client.get(
            f"/api/exam-attempts/"
            f"{started['attemptId']}"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        assert_no_answer_secret(
            self,
            response.get_json()[
                "questions"
            ],
            "resume.questions",
        )

    def test_submit_response_does_not_leak_answer_key(self):
        started = self.start()

        response = self.client.post(
            f"/api/exam-attempts/"
            f"{started['attemptId']}/submit",
            json=submit_payload(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        body = response.get_json()

        self.assertTrue(body["ok"])
        self.assertEqual(
            body["essayCount"],
            1,
        )
        self.assertEqual(
            body["status"],
            "待人工批改",
        )

        assert_no_answer_secret(
            self,
            body["questions"],
            "submit.questions",
        )

    def test_client_cannot_override_server_score(self):
        started = self.start()

        payload = submit_payload(
            answers=[
                0,
                "essay response",
            ]
        )

        payload.update(
            {
                "score": 100,
                "correctCount": 999,
                "wrongCount": 0,
                "status": "合格",
            }
        )

        response = self.client.post(
            f"/api/exam-attempts/"
            f"{started['attemptId']}/submit",
            json=payload,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        result = response.get_json()

        self.assertEqual(
            result["score"],
            0,
        )
        self.assertEqual(
            result["correctCount"],
            0,
        )
        self.assertEqual(
            result["wrongCount"],
            1,
        )
        self.assertEqual(
            result["essayCount"],
            1,
        )
        self.assertEqual(
            result["status"],
            "待人工批改",
        )

    def test_duplicate_submit_only_first_is_accepted(self):
        started = self.start()
        attempt_id = started["attemptId"]

        first = self.client.post(
            f"/api/exam-attempts/"
            f"{attempt_id}/submit",
            json=submit_payload(),
        )

        second = self.client.post(
            f"/api/exam-attempts/"
            f"{attempt_id}/submit",
            json=submit_payload(),
        )

        self.assertEqual(
            first.status_code,
            200,
        )

        self.assertEqual(
            second.status_code,
            409,
        )

        self.assertEqual(
            second.get_json(),
            {
                "error":
                "此考核已經提交，不能重複計分。"
            },
        )

    def test_legacy_question_endpoint_is_sanitized(self):
        response = self.client.get(
            "/api/quiz-questions"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        assert_no_answer_secret(
            self,
            response.get_json(),
            "legacy.questions",
        )

    def test_submission_failure_rolls_back_attempt_state(self):
        started = self.start()
        attempt_id = started["attemptId"]

        with patch.object(
            exam_repo,
            "insert_exam_record",
            side_effect=RuntimeError(
                "simulated DB failure"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                self.client.post(
                    f"/api/exam-attempts/"
                    f"{attempt_id}/submit",
                    json=submit_payload(),
                )

        # Transaction rollback must leave the attempt
        # resumable instead of half-submitted.
        resumed = self.client.get(
            f"/api/exam-attempts/"
            f"{attempt_id}"
        )

        self.assertEqual(
            resumed.status_code,
            200,
        )
        self.assertEqual(
            resumed.get_json()["status"],
            "started",
        )

        conn, _kind = (
            self.base._db_conn()
        )

        try:
            count = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM exam_records
                """
            ).fetchone()["n"]
        finally:
            conn.close()

        self.assertEqual(
            int(count),
            0,
        )


if __name__ == "__main__":
    unittest.main()
