import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CompletionCertificateUi90Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath("static", "system.html").read_text(encoding="utf-8")
        cls.learner = ROOT.joinpath("static", "system-learner.js").read_text(encoding="utf-8")

    def test_certificate_shelf_and_versioned_asset_are_present(self):
        for token in (
            'id="completion-certificates"',
            'id="completion-certificates-count"',
            'id="completion-certificates-list"',
            '/system-learner.js?v=9000',
        ):
            self.assertIn(token, self.html)

    def test_runtime_loads_renders_and_issues_certificates(self):
        for token in (
            "fetch('/api/completion-certificates'",
            "function renderCompletionCertificateShelf()",
            "async function issueCompletionCertificate(courseId)",
            "data-completion-certificate-course",
            "bindCompletionCertificateButtons(cards)",
        ):
            self.assertIn(token, self.learner)
        self.assertIn("/api/completion-certificates/${encodeURIComponent(courseId)}", self.learner)

    def test_ui_exposes_certificate_statuses_and_actions(self):
        for token in ("目前有效", "需重新訓練", "歷史紀錄", "取得完訓證明", "查看完訓證明"):
            self.assertIn(token, self.learner)


if __name__ == "__main__":
    unittest.main()
