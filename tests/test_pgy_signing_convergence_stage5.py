import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class PgySigningConvergenceStage5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = ROOT.joinpath("pgy_signing_66.py").read_text(encoding="utf-8")
        cls.routes = ROOT.joinpath("teacher_app/pgy/routes_signing.py").read_text(encoding="utf-8")
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
        self.assertIn("teacher_app.pgy.routes_signing", self.adapter)
        self.assertNotIn("@app", self.adapter)
        self.assertIn("signing_facade.list_candidates", self.routes)
        self.assertIn("signing_facade.list_assignments", self.routes)
        self.assertIn("signing_facade.get_assignment", self.routes)
        self.assertIn("signing_facade.create_assignment", self.routes)
        self.assertIn("signing_facade.update_assignment", self.routes)

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

    def test_legacy_new_mode_dispatch_is_canonical(self):
        for retired_root_marker in (
            "legacy_teacher_sign",
            "legacy_countersign",
            "legacy_reopen",
            "legacy_update",
            'if mode == "legacy"',
            "signing.sign_assignment",
            "signing.countersign_assignment",
            "signing.reopen_assignment",
        ):
            self.assertNotIn(retired_root_marker, self.routes)

        for canonical_call in (
            "signing_facade.update_assignment",
            "signing_facade.teacher_sign_assignment",
            "signing_facade.countersign_assignment",
            "signing_facade.reopen_assignment",
        ):
            self.assertIn(canonical_call, self.routes)

        for facade_marker in (
            'get_sign_mode(assignment_id) == "legacy"',
            "pgy_service.update_assignment",
            "pgy_service.teacher_sign_assignment",
            "pgy_service.group_countersign_assignment",
            "pgy_service.reopen_assignment",
            "signing.sign_assignment",
            "signing.countersign_assignment",
            "signing.reopen_assignment",
        ):
            self.assertIn(facade_marker, self.facade)


if __name__ == "__main__":
    unittest.main()
