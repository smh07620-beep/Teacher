import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TrainingCompetencyMatrix92Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath("static", "system.html").read_text(encoding="utf-8")
        cls.ui = ROOT.joinpath("static", "admin-competency-matrix-92.js").read_text(
            encoding="utf-8-sig"
        )
        cls.assets = ROOT.joinpath("teacher_app", "frontend", "assets.py").read_text(
            encoding="utf-8"
        )

    def test_matrix_surface_is_available_inside_compliance_workspace(self):
        for marker in (
            "admin-compliance-view-matrix",
            "admin-competency-matrix-view",
            "admin-competency-matrix-table",
            "人員 × 能力矩陣",
            "不等同臨床執業資格",
        ):
            self.assertIn(marker, self.html)

    def test_matrix_reuses_canonical_compliance_api_read_only(self):
        self.assertIn("/api/training-compliance?", self.ui)
        self.assertIn("credentials:'same-origin'", self.ui)
        for marker in (
            "complete",
            "retraining",
            "remediation",
            "awaiting_exam",
            "qualificationStatus",
        ):
            self.assertIn(marker, self.ui)
        for mutation in (
            "method: 'POST'",
            "method: 'PUT'",
            "method: 'PATCH'",
            "method: 'DELETE'",
        ):
            self.assertNotIn(mutation, self.ui)

    def test_matrix_adds_requested_status_levels(self):
        for marker in (
            "未訓練",
            "訓練中",
            "待考核",
            "待評核",
            "已通過",
            "已逾期",
            "需重訓",
            "需補強",
        ):
            self.assertIn(marker, self.ui)

    def test_matrix_adds_filtering_and_gap_views(self):
        for marker in (
            "admin-competency-status-filter",
            "admin-competency-display-filter",
            "只顯示待完成／異常",
            "只顯示已通過",
            "admin-competency-clear-filters",
        ):
            self.assertIn(marker, self.ui)

    def test_matrix_evidence_drilldown_is_read_only(self):
        for marker in (
            "admin-competency-evidence-panel",
            "ASSESSMENT EVIDENCE",
            "評核／批改者",
            "評核時間",
            "評語／備註",
            "reviewerName",
            "reviewedAt",
            "reviewComment",
        ):
            self.assertIn(marker, self.ui)
        self.assertIn("不提供在矩陣直接改寫評核結果或資格狀態", self.ui)

    def test_matrix_asset_loads_after_0091_owner(self):
        self.assertEqual(self.assets.count('"/admin-compliance-91.js"'), 1)
        self.assertEqual(self.assets.count('"/admin-competency-matrix-92.js"'), 1)
        self.assertLess(
            self.assets.index('"/admin-compliance-91.js"'),
            self.assets.index('"/admin-competency-matrix-92.js"'),
        )

    def test_matrix_ui_adds_no_inline_handlers(self):
        for marker in ("onclick=", "onchange=", "oninput="):
            self.assertNotIn(marker, self.ui.lower())


if __name__ == "__main__":
    unittest.main()
