import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def read(name):
    return (STATIC / name).read_text(encoding="utf-8")


class AssessmentPageSlimmingTests(unittest.TestCase):
    def test_tab_bar_replaces_flow_chips_and_review_shortcut(self):
        js = read("teacher-workspace-1014.js")
        self.assertIn("data-assessment-tab-1030", js)
        for label in ("📝 考卷", "待批改", "歷史紀錄", "教學分析"):
            self.assertIn(label, js)
        self.assertNotIn("teacher-assessment-step-1014", js)
        self.assertNotIn("ensureAssessmentReviewShortcut", js)
        self.assertNotIn("評量工作流程", js)

    def test_stat_cards_became_one_summary_line_with_same_ids(self):
        html = read("system.html")
        self.assertIn("admin-quiz-summary-line", html)
        self.assertNotIn('class="admin-quiz-summary-grid"', html)
        for key in ("total", "published", "approved", "draft"):
            self.assertIn(f'id="admin-quiz-{key}-count"', html)
        self.assertIn('id="admin-quiz-sync-status"', html)

    def test_exam_row_has_one_state_based_primary_button(self):
        js = read("admin-question-bank.js")
        self.assertEqual(js.count("data-quiz-primary-1030"), 1)
        labels = set(re.findall(r"primary:'([^']+)'", js))
        self.assertEqual(labels, {"繼續編輯", "發布", "查看考卷"})
        self.assertIn("whitespace-nowrap", js)
        # delete only through the ⋯ menu, which keeps the cascade confirm
        self.assertEqual(js.count('data-csp-click="adminDeleteQuizCategory'), 1)

    def test_pending_badge_event_is_wired(self):
        self.assertIn("teacher-assessment-pending-1030", read("admin-question-bank.js"))
        self.assertIn("teacher-assessment-pending-1030", read("teacher-workspace-1014.js"))

    def test_legacy_ids_other_modules_rely_on_still_exist(self):
        js = read("teacher-workspace-1014.js")
        for ident in ("teacher-assessment-flow-1014", "teacher-open-pending-review-1014", "teacher-open-review-1014"):
            self.assertIn(ident, js)


if __name__ == "__main__":
    unittest.main()
