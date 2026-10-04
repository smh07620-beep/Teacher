import unittest
from pathlib import Path


ROOT=Path(__file__).parents[1]


class F3TrainingInterventionUiTests(unittest.TestCase):
    def test_competency_evidence_emits_intervention_hook(self):
        source=ROOT.joinpath("static","admin-competency-matrix-92.js").read_text(encoding="utf-8")
        self.assertIn("admin-training-intervention-f3",source)
        self.assertIn("training-intervention:evidence",source)
        self.assertIn("不提供在矩陣直接改寫評核結果或資格狀態",source)
        self.assertIn("介入追蹤只記錄處理流程，不會改寫原始證據",source)

    def test_intervention_ui_supports_full_case_actions(self):
        source=ROOT.joinpath("static","training-intervention-f3.js").read_text(encoding="utf-8")
        for marker in (
            "建立介入追蹤",
            "開始追蹤",
            "準備再測",
            "嘗試結案",
            "取消案件",
            "給學員的訊息",
            "內部追蹤備註",
        ):
            self.assertIn(marker,source)
        self.assertIn("/api/training-interventions",source)

    def test_asset_is_registered_after_competency_matrix(self):
        source=ROOT.joinpath("teacher_app","frontend","assets.py").read_text(encoding="utf-8")
        matrix=source.index('"/admin-competency-matrix-92.js"')
        intervention=source.index('"/training-intervention-f3.js"')
        self.assertLess(matrix,intervention)


if __name__=="__main__":
    unittest.main()
