from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ExamResultHistoryAndAtlasReview1035Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exam = (ROOT / "static" / "system-exam.js").read_text(encoding="utf-8")
        cls.review = (ROOT / "static" / "review-links-66.js").read_text(encoding="utf-8")
        cls.results = (ROOT / "static" / "admin-results-data.js").read_text(encoding="utf-8")
        cls.workspace = (ROOT / "static" / "admin-results-workspace.js").read_text(encoding="utf-8")

    def test_student_keeps_server_answer_details_for_remediation(self):
        self.assertIn("window.currentExamAnswerDetails", self.exam)

    def test_atlas_review_is_only_shown_for_wrong_answers(self):
        self.assertIn("detail && detail.isCorrect !== false", self.review)
        self.assertIn("建議回到圖譜重新判讀", self.review)
        self.assertIn("回到圖譜複習", self.review)

    def test_teacher_view_collapses_attempt_history(self):
        self.assertIn("function collapseExamHistory(records)", self.results)
        self.assertIn("const passed = completed.filter", self.results)
        self.assertIn("let visibleRecords=collapseExamHistory(records);", self.results)
        self.assertIn("完整歷史仍保留在系統", self.workspace)


if __name__ == "__main__":
    unittest.main()
