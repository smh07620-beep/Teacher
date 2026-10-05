from pathlib import Path
import unittest

from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class LegacyAdminEntrypoint404CompatTests(unittest.TestCase):
    def test_retired_admin_entrypoint_resolves_without_becoming_a_current_asset(self):
        path = ROOT / "static" / "admin-entrypoint-69.js"
        self.assertTrue(path.exists())
        source = path.read_text(encoding="utf-8")
        self.assertIn("Legacy admin entrypoint compatibility shim", source)
        self.assertIn("renderAdminSystemStatus", source)
        self.assertIn("ProductionReadinessF6", source)
        self.assertIn("AdminEntrypoint69Compat", source)
        self.assertNotIn("/admin-entrypoint-69.js", ASSET_MANIFEST["system"]["body"])

    def test_current_system_probes_have_canonical_backend_owners(self):
        health = ROOT.joinpath("teacher_app", "maintenance", "health.py").read_text(encoding="utf-8")
        storage = ROOT.joinpath("teacher_app", "storage", "admin_routes.py").read_text(encoding="utf-8")
        questions = ROOT.joinpath("teacher_app", "assessments", "runtime_question_routes.py").read_text(encoding="utf-8")
        readiness = ROOT.joinpath("teacher_app", "maintenance", "production_readiness_routes.py").read_text(encoding="utf-8")
        bank = ROOT.joinpath("teacher_app", "assessments", "question_bank_routes.py").read_text(encoding="utf-8")

        self.assertIn('"/health"', health)
        self.assertIn('"/api/storage-status"', storage)
        self.assertIn('"/api/ai-questions/status"', questions)
        self.assertIn('"/api/production-readiness"', readiness)
        self.assertIn("register_runtime_question_routes(", bank)


if __name__ == "__main__":
    unittest.main()
