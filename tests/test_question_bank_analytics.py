"""Behavior coverage for canonical Question Bank item analytics."""
import unittest
from unittest.mock import patch

from teacher_app.assessments import analytics


class QuestionBankAnalyticsTests(unittest.TestCase):
    @patch(
        "teacher_app.assessments.analytics.repository.current_question_version_identity",
        return_value={"version": 1, "questionHash": "hash-1"},
    )
    @patch("teacher_app.assessments.analytics.repository.list_question_attempt_analytics")
    def test_fewer_than_ten_attempts_keeps_data_insufficient_contract(
        self,
        list_attempts,
        _identity,
    ):
        list_attempts.return_value = [
            {"selected_option": "0", "is_correct": 0}
            for _ in range(9)
        ]

        payload = analytics.get_question_analytics("q-1")

        self.assertEqual(payload["attemptCount"], 9)
        self.assertFalse(payload["sufficientData"])
        self.assertEqual(payload["message"], "資料不足")
        self.assertEqual(payload["questionVersion"], 1)
        self.assertEqual(payload["questionHash"], "hash-1")

    @patch(
        "teacher_app.assessments.analytics.repository.get_question_version_options",
        return_value=["A", "B"],
    )
    @patch(
        "teacher_app.assessments.analytics.repository.get_question_version_correct",
        return_value=1,
    )
    @patch(
        "teacher_app.assessments.analytics.repository.current_question_version_identity",
        return_value={"version": 1, "questionHash": "hash-1"},
    )
    @patch("teacher_app.assessments.analytics.repository.list_question_attempt_analytics")
    def test_sufficient_attempts_keep_rate_counts_and_distractor_contract(
        self,
        list_attempts,
        _identity,
        _get_correct,
        _get_options,
    ):
        list_attempts.return_value = (
            [{"selected_option": "1", "is_correct": 1, "attempt_score": 90 + i, "response_seconds": 20 + i} for i in range(6)]
            + [{"selected_option": "0", "is_correct": 0, "attempt_score": 40 + i, "response_seconds": 30 + i} for i in range(4)]
        )

        payload = analytics.get_question_analytics("q-1")

        self.assertEqual(payload["attemptCount"], 10)
        self.assertTrue(payload["sufficientData"])
        self.assertEqual(payload["correctRate"], 0.6)
        self.assertEqual(payload["difficultyP"], 0.6)
        self.assertEqual(payload["exposureCount"], 10)
        self.assertEqual(payload["discriminationD"], 1.0)
        self.assertIsInstance(payload["averageResponseSeconds"], float)
        self.assertEqual(payload["optionSelectionCounts"], {"1": 6, "0": 4})
        self.assertEqual(payload["distractorDistribution"], {"0": 4})
        self.assertEqual(payload["distractorEffectiveness"], 1.0)
        self.assertEqual(payload["questionVersion"], 1)
        self.assertEqual(payload["questionHash"], "hash-1")

    def test_balanced_selection_weight_is_neutral_without_sufficient_data(self):
        self.assertEqual(
            analytics.balanced_selection_weight({"sufficientData": False}),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
