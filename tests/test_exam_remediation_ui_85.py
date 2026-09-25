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
        cls.notifications = ROOT.joinpath("static", "notification-center-71.js").read_text(encoding="utf-8")

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
        self.assertIn("x.remediationRequired", self.portal)
        self.assertIn("補強再測", self.portal)
        self.assertIn("exam?.remediationRequired", self.notifications)
        self.assertIn("補強後再測", self.notifications)


if __name__ == "__main__":
    unittest.main()
