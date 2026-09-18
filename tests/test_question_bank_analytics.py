"""Behavior coverage for canonical Question Bank item analytics."""
import unittest
from unittest.mock import patch

from teacher_app.assessments import analytics


class QuestionBankAnalyticsTests(unittest.TestCase):
    @patch("teacher_app.assessments.analytics.repository.get_bank_question_correct")
    @patch("teacher_app.assessments.analytics.repository.list_question_attempt_analytics")
    def test_fewer_than_ten_attempts_keeps_data_insufficient_contract(
        self,
        list_attempts,
        get_correct,
    ):
        list_attempts.return_value = [
            {"selected_option": "0", "is_correct": 0}
            for _ in range(9)
        ]

        payload = analytics.get_question_analytics("q-1")

        self.assertEqual(payload, {
            "attemptCount": 9,
            "sufficientData": False,
            "message": "資料不足",
        })
        get_correct.assert_not_called()

    @patch(
        "teacher_app.assessments.analytics.repository.get_bank_question_correct",
        return_value=1,
    )
    @patch("teacher_app.assessments.analytics.repository.list_question_attempt_analytics")
    def test_sufficient_attempts_keep_rate_counts_and_distractor_contract(
        self,
        list_attempts,
        _get_correct,
    ):
        list_attempts.return_value = (
            [{"selected_option": "1", "is_correct": 1} for _ in range(6)]
            + [{"selected_option": "0", "is_correct": 0} for _ in range(4)]
        )

        payload = analytics.get_question_analytics("q-1")

        self.assertEqual(payload["attemptCount"], 10)
        self.assertTrue(payload["sufficientData"])
        self.assertEqual(payload["correctRate"], 0.6)
        self.assertEqual(payload["optionSelectionCounts"], {"1": 6, "0": 4})
        self.assertEqual(payload["distractorDistribution"], {"0": 4})


if __name__ == "__main__":
    unittest.main()
