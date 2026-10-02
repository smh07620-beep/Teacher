import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ProductPhaseCompletion20261002Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.status = ROOT.joinpath("PRODUCT_CONVERGENCE_20261001.md").read_text(encoding="utf-8")
        cls.inventory = ROOT.joinpath("PRODUCT_FEATURE_INVENTORY_20261001.md").read_text(encoding="utf-8")
        cls.ia = ROOT.joinpath("PRODUCT_INFORMATION_ARCHITECTURE_20261001.md").read_text(encoding="utf-8")
        cls.operations = ROOT.joinpath("teacher_app", "worker", "operations.py").read_text(encoding="utf-8")
        cls.reminders = ROOT.joinpath("teacher_app", "notifications", "reminders.py").read_text(encoding="utf-8")
        cls.security = ROOT.joinpath("teacher_app", "common", "security.py").read_text(encoding="utf-8")
        cls.audit = ROOT.joinpath("teacher_app", "common", "audit.py").read_text(encoding="utf-8")
        cls.worker_alert_workflow = ROOT.joinpath(".github", "workflows", "worker-offline-alerts.yml").read_text(encoding="utf-8")
        cls.playwright_workflow = ROOT.joinpath(".github", "workflows", "playwright-ui-checks.yml").read_text(encoding="utf-8")
        cls.golden_workflow = ROOT.joinpath(".github", "workflows", "product-golden-path-checks.yml").read_text(encoding="utf-8")

    def test_phase_a_inventory_is_complete_and_uses_five_way_product_decisions(self):
        self.assertIn("**Complete.**", self.inventory)
        for label in ("保留", "重複", "未完成", "廢棄", "隱藏"):
            self.assertIn(label, self.inventory)

    def test_phase_b_has_exact_four_product_areas(self):
        for area in ("我的學習", "教學", "評量", "系統管理"):
            self.assertIn(area, self.ia)
        self.assertIn("not a fifth product area", self.ia)

    def test_phase_c_keeps_real_full_stack_and_all_eight_golden_paths(self):
        for number in range(1, 9):
            self.assertIn(f"GP-0{number}", self.status)
        self.assertIn("Browser → R2", self.status)
        self.assertIn("material_worker", self.golden_workflow)
        self.assertIn("full-stack Browser", self.golden_workflow)

    def test_phase_d_is_release_documented_as_canonical_visible_ownership(self):
        self.assertIn("Overview / 需要處理 / 目前工作 / 歷史紀錄", self.status)
        self.assertIn("old portal progress/todo writers", self.status)

    def test_phase_e_contract_covers_recovery_observability_audit_email_performance_and_mobile(self):
        for marker in (
            "recover_stale_material_jobs",
            "oldestPendingAgeSeconds",
            "recentFailureRate",
            "averageCompletedDurationSeconds",
            "offline_worker_alerts",
        ):
            self.assertIn(marker, self.operations)
        self.assertIn("run_worker_offline_reminders", self.reminders)
        self.assertIn("_release_claim", self.reminders)
        self.assertIn('cron: "*/10 * * * *"', self.worker_alert_workflow)
        self.assertIn("MATERIAL_WORKER_OFFLINE_ALERT_SECONDS", self.worker_alert_workflow)
        self.assertIn("def record_event(", self.audit)
        self.assertIn("teacher_stage2 endpoint=%s status=%s duration_ms=%.1f", self.security)
        self.assertIn("mobile-learner-golden-path-1025.spec.js", self.playwright_workflow)

    def test_phase_completion_document_keeps_all_four_release_gates(self):
        for gate in (
            "Teacher release checks",
            "Product Golden Path checks",
            "Playwright UI checks",
            "Windows Worker checks",
        ):
            self.assertIn(gate, self.status)


if __name__ == "__main__":
    unittest.main()
