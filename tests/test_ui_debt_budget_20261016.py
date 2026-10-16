"""UI debt may only go down: lower these numbers whenever a screen is cleaned up."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ui_debt_report  # noqa: E402

BUDGET = {
    "patchFiles": 11,
    "mutationObserverFiles": 35,
    "importantDeclarations": 544,
    "tinyTextClasses": 726,
}


class UiDebtBudgetTests(unittest.TestCase):
    def test_debt_does_not_grow(self):
        current = ui_debt_report.measure()
        over = {k: (current[k], limit) for k, limit in BUDGET.items() if current[k] > limit}
        self.assertEqual({}, over, "UI debt grew (current, budget): fix it or clean up elsewhere first")


if __name__ == "__main__":
    unittest.main()
