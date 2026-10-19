"""Whole-exam question health check (2026-10-17)."""
import unittest
from unittest import mock

from teacher_app.assessments import analytics


class ItemReportTests(unittest.TestCase):
    def test_flags_and_ordering(self):
        metrics = {
            "a": {"attemptCount": 30, "sufficientData": True, "difficultyP": 0.95, "correctRate": 0.95, "discriminationD": 0.3, "distractorEffectiveness": 1.0},
            "b": {"attemptCount": 30, "sufficientData": True, "difficultyP": 0.5, "correctRate": 0.5, "discriminationD": -0.2, "distractorEffectiveness": 1.0},
            "c": {"attemptCount": 3, "sufficientData": False},
            "d": {"attemptCount": 30, "sufficientData": True, "difficultyP": 0.6, "correctRate": 0.6, "discriminationD": 0.4, "distractorEffectiveness": 1.0},
        }
        questions = [{"id": k, "question": k} for k in "abcd"]
        with mock.patch.object(analytics.repository, "list_questions", return_value=questions), \
             mock.patch.object(analytics, "get_question_analytics", side_effect=lambda qid: metrics[qid]):
            report = analytics.item_report("cat")
        order = [item["questionId"] for item in report["items"]]
        self.assertEqual(order[0], "b")  # reversed discrimination is the most urgent
        self.assertEqual(order[1], "a")
        self.assertEqual(report["flaggedCount"], 2)
        self.assertEqual(report["insufficientCount"], 1)
        self.assertEqual([f["code"] for f in report["items"][0]["flags"]], ["reverse"])
        healthy = next(i for i in report["items"] if i["questionId"] == "d")
        self.assertEqual(healthy["flags"], [])

    def test_route_is_group_scoped(self):
        src = open("teacher_app/assessments/question_bank_routes.py", encoding="utf-8").read()
        block = src[src.index('/item-report")'):src.index('/api/question-bank/<question_id>/versions')]
        self.assertIn("scope_filter.scoped_groups", block)


if __name__ == "__main__":
    unittest.main()
