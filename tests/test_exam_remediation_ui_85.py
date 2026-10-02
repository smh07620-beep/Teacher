import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExamRemediationUi85Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath("static", "system.html").read_text(encoding="utf-8")
        cls.exam = ROOT.joinpath("static", "system-exam.js").read_text(encoding="utf-8")
        cls.csp = ROOT.joinpath("static", "system-csp-actions.js").read_text(encoding="utf-8")
        cls.portal = ROOT.joinpath("static", "portal-v56.js").read_text(encoding="utf-8")
        cls.todo = ROOT.joinpath("static", "learner-todo-convergence-1025.js").read_text(encoding="utf-8")
        cls.notifications = ROOT.joinpath("static", "notification-center-71.js").read_text(encoding="utf-8")
        cls.notification_events = ROOT.joinpath("teacher_app", "notifications", "events.py").read_text(encoding="utf-8")

    def test_result_dashboard_has_remediation_surface(self):
        for token in (
            'id="result-remediation"',
            'id="result-remediation-summary"',
            'id="result-remediation-list"',
            'openExamRemediationMaterials()',
            'restartExamAfterRemediation()',
        ):
            self.assertIn(token, self.html)

    def test_exam_runtime_renders_and_preserves_failed_history_message(self):
        self.assertIn("window.currentExamRemediationPlan=result.remediation||null", self.exam)
        self.assertIn("function renderExamRemediation(plan)", self.exam)
        self.assertIn("原始成績紀錄會保留", self.exam)
        self.assertIn("window.openExamRemediationMaterials=function()", self.exam)
        self.assertIn("window.restartExamAfterRemediation=function()", self.exam)

    def test_csp_dispatcher_allows_remediation_actions(self):
        self.assertIn("'openExamRemediationMaterials'", self.csp)
        self.assertIn("'restartExamAfterRemediation'", self.csp)

    def test_home_and_notification_distinguish_remediation_retry(self):
        self.assertNotIn("renderPendingExams(", self.portal)
        self.assertIn("item?.status==='remediation'?'補強再測':'考核'", self.todo)
        self.assertIn("補強再測", self.todo)
        self.assertIn('exam.get("remediationRequired")', self.notification_events)
        self.assertIn('"remediation" if exam.get("remediationRequired") else "pending"', self.notification_events)
        self.assertIn('"補強再測"', self.notification_events)
        self.assertIn("item.kind==='exam'", self.notifications)
        self.assertIn("item.badge", self.notifications)


if __name__ == "__main__":
    unittest.main()
