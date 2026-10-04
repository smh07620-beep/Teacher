import unittest
from pathlib import Path


ROOT=Path(__file__).parents[1]


class F6ProductionGateTests(unittest.TestCase):
    def test_reference_integrity_and_restore_rehearsal_are_required(self):
        source=ROOT.joinpath("teacher_app","maintenance","production_readiness.py").read_text(encoding="utf-8")
        self.assertIn('"restore_rehearsal"',source)
        self.assertIn('"reference_integrity"',source)
        self.assertIn('"productionReady"',source)

    def test_system_dashboard_surfaces_live_production_gate(self):
        source=ROOT.joinpath("static","production-readiness-f6.js").read_text(encoding="utf-8")
        self.assertIn("/api/production-readiness",source)
        self.assertIn("F6 Production Readiness",source)
        self.assertIn("PRODUCTION READY",source)
        self.assertIn("BLOCKED",source)

    def test_asset_loads_after_worker_status_owner(self):
        source=ROOT.joinpath("teacher_app","frontend","assets.py").read_text(encoding="utf-8")
        worker=source.index('"/worker-status-70.js"')
        f6=source.index('"/production-readiness-f6.js"')
        self.assertLess(worker,f6)

    def test_gp10_runs_all_f6_contracts(self):
        source=ROOT.joinpath(".github","workflows","product-golden-path-checks.yml").read_text(encoding="utf-8")
        self.assertIn("GP-10 production readiness, content governance, and recovery contracts",source)
        self.assertIn("test_f6_*.py",source)

    def test_operator_acceptance_document_has_two_gate_contract(self):
        source=ROOT.joinpath("docs","PRODUCTION_READINESS_F6.md").read_text(encoding="utf-8")
        self.assertIn("Gate 1 — pre-deploy",source)
        self.assertIn("Gate 2 — post-deploy",source)
        self.assertIn("restore/rehearsal",source)
        self.assertIn("recovery-audit",source)


if __name__=="__main__":
    unittest.main()
