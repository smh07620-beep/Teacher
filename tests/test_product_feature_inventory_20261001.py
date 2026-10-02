import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
RC = ROOT.joinpath("RC_FEATURE_UI_COVERAGE_MATRIX.md")
PRODUCT = ROOT.joinpath("PRODUCT_FEATURE_INVENTORY_20261001.md")


class ProductFeatureInventory20261001Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rc = RC.read_text(encoding="utf-8")
        cls.product = PRODUCT.read_text(encoding="utf-8")

    def test_required_product_decisions_are_explicit(self):
        for label in ("保留", "重複", "未完成", "廢棄", "隱藏"):
            self.assertIn(label, self.product)

    def test_every_current_rc_row_status_has_a_product_decision_mapping(self):
        statuses = set()
        for line in self.rc.splitlines():
            if not line.startswith("|") or line.startswith("| ---") or "Backend / runtime owner" in line:
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 7:
                statuses.add(cells[-1].strip("`"))
        self.assertTrue(statuses, "RC matrix must contain product rows")
        self.assertEqual(statuses, {"Usable", "Internal", "Compatibility", "Deferred"})
        mappings = {
            "Usable": "**保留**",
            "Internal": "**隱藏**",
            "Compatibility": "**隱藏**",
            "Deferred": "**未完成**",
        }
        for status, decision in mappings.items():
            self.assertRegex(
                self.product,
                rf"\| `{re.escape(status)}` \| {re.escape(decision)} \|",
                msg=f"missing product decision for RC status {status}",
            )

    def test_known_duplicate_and_retired_owners_are_not_silently_promoted(self):
        for marker in (
            "static/portal-v56.js",
            "static/learning-progress-convergence-1025.js",
            "static/learner-todo-convergence-1025.js",
            "Legacy root compatibility modules",
            "old question drawer/overlay",
            "pgy_atomic.py",
            "getAdminKey()",
            "X-Admin-Key",
        ):
            self.assertIn(marker, self.product)
        self.assertIn("**重複**", self.product)
        self.assertIn("**廢棄**", self.product)

    def test_teacher_learners_is_promoted_but_remaining_p2_capabilities_stay_unfinished(self):
        self.assertIn("我的學員 — 保留（第一階段完成）", self.product)
        for marker in ("臨床技能評核", "能力追蹤", "教學分析"):
            self.assertIn(marker, self.product)
        self.assertIn("These remain **未完成**", self.product)


if __name__ == "__main__":
    unittest.main()
