from pathlib import Path
import unittest

from pgy_frontend import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class Phase3XLearnerResultChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "learner-result-chart.js").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github" / "workflows" / "phase3-pgy-checks.yml").read_text(encoding="utf-8")
        cls.exam_runtime = (ROOT / "static" / "system-exam.js").read_text(encoding="utf-8")

    def test_preserves_the_shared_learner_result_global(self):
        self.assertIn("window.renderCategoryChart", self.source)
        self.assertIn("renderCategoryChart(result.categoryStats||{})", self.exam_runtime)

    def test_preserves_chart_replacement_and_category_score_contracts(self):
        for contract in (
            "if (chartInstance)",
            "chartInstance.destroy()",
            "Object.keys(categoryStats)",
            "categoryStats[cat].correct",
            "categoryStats[cat].total",
            "chartInstance = new Chart",
            "type: 'bar'",
        ):
            self.assertIn(contract, self.source)

    def test_module_does_not_introduce_api_rbac_or_wizard_policy(self):
        for forbidden in ("fetch(", "getAdminKey", "X-Admin-Key", "professional_title", "responsibility_tags", "hasPermission", "upload"):
            self.assertNotIn(forbidden, self.source)

    def test_asset_is_injected_and_syntax_checked(self):
        self.assertIn('/learner-result-chart.js', ASSET_MANIFEST["system"]["body"])
        self.assertIn("find static -type f -name '*.js'", self.workflow)


if __name__ == "__main__":
    unittest.main()
