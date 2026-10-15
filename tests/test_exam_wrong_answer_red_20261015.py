"""After submitting, wrong answers are marked red (2026-10-15). Only correctness is shown, never the answer key."""
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "static" / "system-exam.js").read_text(encoding="utf-8")


class WrongAnswerRedTests(unittest.TestCase):
    def test_verdict_comes_from_server_flag(self):
        self.assertIn("function examQuestionVerdict", SRC)
        self.assertIn("typeof r.isCorrect==='boolean'", SRC)

    def test_wrong_choice_is_red_and_correct_is_green(self):
        self.assertIn("verdict===false?'border-2 border-rose-400 bg-rose-50", SRC)
        self.assertIn("verdict===true?'border-2 border-emerald-400 bg-emerald-50", SRC)
        self.assertIn("✕ 答錯", SRC)

    def test_review_flags_set_before_rerender(self):
        self.assertLess(SRC.index("window.currentExamReviewQuestions=Array.isArray(result.reviewQuestions)"),
                        SRC.index("clearExamDraft(currentCatKey);\n    renderQuestions();"))

    def test_server_still_returns_no_answer_key_in_review_flags(self):
        service = (Path(__file__).resolve().parents[1] / "teacher_app" / "exams" / "service.py").read_text(encoding="utf-8")
        block = service[service.index("review_questions.append({"):][:500]
        self.assertIn('"isCorrect"', block)
        self.assertNotIn('"answer"', block)


if __name__ == "__main__":
    unittest.main()
