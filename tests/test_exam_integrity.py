import unittest
from teacher_app.exams.grading import sanitize_question, score_question


class ExamIntegrityTests(unittest.TestCase):
    def test_learner_question_removes_answer_keys(self):
        q = {
            "question": "Q",
            "correct": 2,
            "explanation": "Because C",
            "answerConfig": {"correctIndices": [1, 2], "acceptedAnswers": ["secret"], "mediaUrl": "/x.mp4", "pauseAt": 12},
        }
        safe = sanitize_question(q)
        self.assertNotIn("correct", safe)
        self.assertNotIn("explanation", safe)
        self.assertNotIn("correctIndices", safe["answerConfig"])
        self.assertNotIn("acceptedAnswers", safe["answerConfig"])
        self.assertEqual(safe["answerConfig"]["mediaUrl"], "/x.mp4")

    def test_server_scores_single_choice(self):
        q = {"questionType": "choice", "correct": 1, "answerConfig": {}}
        self.assertTrue(score_question(q, 1))
        self.assertFalse(score_question(q, 0))

    def test_server_scores_multi_as_exact_set(self):
        q = {"questionType": "multi", "answerConfig": {"correctIndices": [0, 2]}}
        self.assertTrue(score_question(q, [2, 0]))
        self.assertFalse(score_question(q, [0]))

    def test_fill_respects_case_sensitivity(self):
        q = {"questionType": "fill", "answerConfig": {"acceptedAnswers": ["HbA1c"], "caseSensitive": False}}
        self.assertTrue(score_question(q, "hba1c"))
        q["answerConfig"]["caseSensitive"] = True
        self.assertFalse(score_question(q, "hba1c"))

    def test_essay_is_not_auto_graded(self):
        self.assertIsNone(score_question({"questionType": "essay", "answerConfig": {}}, "text"))


if __name__ == "__main__":
    unittest.main()
