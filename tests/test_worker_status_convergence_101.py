import unittest
from pathlib import Path

from pgy_frontend import ASSET_MANIFEST

ROOT = Path(__file__).parents[1]


class WorkerStatusConvergenceTests(unittest.TestCase):
    def test_convergence_layer_loads_after_worker_status_runtime(self):
        body = ASSET_MANIFEST["system"]["body"]
        base = body.index("/worker-status-70.js")
        convergence = body.index("/worker-status-convergence-101.js")
        self.assertLess(base, convergence)

    def test_worker_status_surface_uses_four_human_product_states(self):
        source = ROOT.joinpath("static", "worker-status-convergence-101.js").read_text(encoding="utf-8")
        self.assertIn("等待處理", source)
        self.assertIn("處理中", ROOT.joinpath("static", "worker-status-70.js").read_text(encoding="utf-8"))
        self.assertIn("可使用", source)
        self.assertIn("需要處理", source)
        self.assertIn("查看處理細節", source)
        self.assertIn("MutationObserver", source)
        self.assertNotIn("X-Admin-Key", source)
        self.assertNotIn("getAdminKey", source)


if __name__ == "__main__":
    unittest.main()
