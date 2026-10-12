from pathlib import Path
import unittest

STATIC = Path(__file__).resolve().parents[1] / "static"


class ResultActionsForLearners(unittest.TestCase):
    def test_result_page_has_no_review_or_admin_buttons(self):
        html = (STATIC / "system.html").read_text(encoding="utf-8")
        start = html.index('id="result-dashboard"')
        block = html[start:start + 6000]
        self.assertNotIn("前往成績後台", block)
        self.assertNotIn("逐題檢視解析", block)
        self.assertIn('id="result-actions"', block)

    def test_retake_only_shown_when_below_passing_score(self):
        js = (STATIC / "system-exam.js").read_text(encoding="utf-8")
        self.assertIn("resultActions.classList.toggle('hidden',!(essayCount<=0&&totalScore<passingScore))", js)


if __name__ == "__main__":
    unittest.main()


class NoRetakeHintForPassers(unittest.TestCase):
    def test_locked_status_does_not_point_to_a_retake_button(self):
        js = (STATIC / "system-exam.js").read_text(encoding="utf-8")
        self.assertNotIn("重測當前考卷", js)
