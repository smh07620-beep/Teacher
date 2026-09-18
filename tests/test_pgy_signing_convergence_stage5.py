import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class PgySigningConvergenceStage5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = ROOT.joinpath("pgy_signing_66.py").read_text(encoding="utf-8")
        cls.facade = ROOT.joinpath("teacher_app/pgy/signing_facade.py").read_text(encoding="utf-8")
        cls.repo = ROOT.joinpath("teacher_app/pgy/signing_repository.py").read_text(encoding="utf-8")

    def test_root_signing_layer_has_no_runtime_sql(self):
        for token in (
            "SELECT ",
            "INSERT INTO",
            "UPDATE pgy_assignments",
            "FROM user_accounts",
        ):
            self.assertNotIn(token, self.adapter)
        self.assertIn("signing_facade.list_candidates", self.adapter)
        self.assertIn("signing_facade.list_assignments", self.adapter)
        self.assertIn("signing_facade.get_assignment", self.adapter)
        self.assertIn("signing_facade.create_assignment", self.adapter)
        self.assertIn("signing_facade.update_sign_mode", self.adapter)

    def test_multi_role_scope_is_canonical(self):
        self.assertIn("user_roles(actor)", self.facade)
        self.assertIn('"education_admin" not in roles', self.facade)
        self.assertIn('"clinical_teacher" in roles', self.facade)
        self.assertIn('"group_leader" in roles', self.facade)
        self.assertNotIn("base.", self.facade)

    def test_candidate_repository_is_multi_role_aware(self):
        self.assertIn("roles_json", self.repo)
        self.assertIn("user_roles", self.repo)
        self.assertIn('"student" in roles', self.repo)
        self.assertIn('"clinical_teacher" in roles', self.repo)
        self.assertNotIn("base.", self.repo)

    def test_adapter_keeps_only_legacy_mode_fallback(self):
        self.assertIn('if mode == "legacy"', self.adapter)
        self.assertIn("legacy_teacher_sign", self.adapter)
        self.assertIn("legacy_countersign", self.adapter)
        self.assertIn("legacy_reopen", self.adapter)
        self.assertIn("legacy_update", self.adapter)
        self.assertIn("signing.sign_assignment", self.adapter)
        self.assertIn("signing.countersign_assignment", self.adapter)
        self.assertIn("signing.reopen_assignment", self.adapter)


if __name__ == "__main__":
    unittest.main()
