import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TeacherReviewActivityMergeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath("static", "system.html").read_text(encoding="utf-8")
        cls.people = ROOT.joinpath("static", "admin-people.js").read_text(encoding="utf-8")

    def test_activity_summary_is_inside_results_workspace_not_people_workspace(self):
        results_start = self.html.index('id="admin-section-results"')
        people_start = self.html.index('id="admin-section-people"')
        activity = self.html.index('id="teacher-activity-overview"')
        summary = self.html.index('id="admin-people-summary"')
        body = self.html.index('id="admin-people-body"')
        self.assertLess(results_start, activity)
        self.assertLess(activity, people_start)
        self.assertLess(results_start, summary)
        self.assertLess(summary, people_start)
        self.assertLess(results_start, body)
        self.assertLess(body, people_start)
        self.assertEqual(self.html.count('id="admin-people-summary"'), 1)
        self.assertEqual(self.html.count('id="admin-people-body"'), 1)

    def test_teacher_activity_is_compact_and_recent_people_are_collapsible(self):
        self.assertIn('id="teacher-activity-details"', self.html)
        self.assertIn('查看近期受評人員', self.html)
        self.assertIn('class="grid grid-cols-3 gap-2 mt-3"', self.html)
        self.assertIn('renderAdminTable()', self.html)

    def test_people_module_exposes_pure_activity_renderer_and_human_role_labels(self):
        self.assertIn('function renderAdminActivitySummary(records)', self.people)
        self.assertIn('window.renderAdminActivitySummary=renderAdminActivitySummary', self.people)
        self.assertIn('await renderAdminUserAccounts()', self.people)
        self.assertIn('USER_ROLE_LABELS[x.role]', self.people)


if __name__ == "__main__":
    unittest.main()
