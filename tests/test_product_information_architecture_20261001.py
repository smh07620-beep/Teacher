import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
IA = ROOT.joinpath("PRODUCT_INFORMATION_ARCHITECTURE_20261001.md")


class ProductInformationArchitecture20261001Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = IA.read_text(encoding="utf-8")

    def test_exactly_four_human_product_areas_are_formalized(self):
        for heading in (
            "## 1. 我的學習",
            "## 2. 教學",
            "## 3. 評量",
            "## 4. 系統管理",
        ):
            self.assertEqual(self.source.count(heading), 1)
        self.assertIn("Teacher has exactly four human-facing product areas", self.source)

    def test_program_group_and_technical_names_are_scope_not_new_areas(self):
        for marker in (
            "PGY",
            "院內教育訓練 / internal",
            "生化、鏡檢、血清、血庫、細菌、血液組",
            "Worker / R2 / MEGA / Google Drive / AI provider",
            "Scope is not information architecture",
        ):
            self.assertIn(marker, self.source)

    def test_teacher_and_system_boundaries_stay_focused(self):
        self.assertIn("daily teaching/course/question work is not duplicated into system navigation", self.source)
        self.assertIn("system administrators may operate platform data but never replace a clinical", self.source)
        self.assertIn("media and paper", self.source)
        self.assertIn("contextual", self.source)

    def test_dual_role_contract_is_persona_switch_not_role_mutation(self):
        self.assertIn("switches persona without role mutation", self.source)
        self.assertIn("without leaking", self.source)


if __name__ == "__main__":
    unittest.main()
