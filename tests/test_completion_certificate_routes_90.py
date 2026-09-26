import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CompletionCertificateRoutes90Tests(unittest.TestCase):
    def test_factory_registers_migration_and_routes(self):
        factory = ROOT.joinpath("teacher_app", "factory.py").read_text(encoding="utf-8")
        self.assertIn("completion_certificate_migration", factory)
        self.assertIn("register_completion_certificate_routes", factory)
        self.assertIn("app = register_completion_certificate_routes(app)", factory)

    def test_release_contract_requires_0090(self):
        contract = ROOT.joinpath("release_contract.py").read_text(encoding="utf-8")
        self.assertIn('"0090-completion-certificates"', contract)

    def test_routes_are_authenticated_user_scoped(self):
        routes = ROOT.joinpath("teacher_app", "learning", "certificate_routes.py").read_text(encoding="utf-8")
        self.assertIn('"/api/completion-certificates"', routes)
        self.assertIn('"/api/completion-certificates/<course_id>"', routes)
        self.assertIn("certificate_service.list_certificates(_current_user(owner))", routes)
        self.assertIn("certificate_service.issue_certificate(_current_user(owner), course_id)", routes)


if __name__ == "__main__":
    unittest.main()
