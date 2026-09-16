"""Regression policy for the phase-1 stale root mirror cleanup.

This is intentionally structural: it protects the production compatibility
seams without pretending that the deferred root modules have already moved.
"""

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def module_functions(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


class RootMirrorPolicyTests(unittest.TestCase):
    def test_ownership_matrix_records_canonical_and_deferred_domains(self):
        document = ROOT.joinpath("ARCHITECTURE_ROOT_MIRROR_CLEANUP.md").read_text(encoding="utf-8")
        for marker in (
            "pgy_app:app",
            "teacher_app.auth.service",
            "teacher_app.common.auth",
            "teacher_app.exams",
            "teacher_app.pgy.service",
            "Frozen / converged",
            "Deferred debt",
            "professional_title",
            "responsibility_tags",
        ):
            self.assertIn(marker, document)

    def test_live_auth_routes_are_thin_canonical_delegates(self):
        functions = module_functions(ROOT / "app.py")
        expected_calls = {
            "api_auth_me": "auth_routes.me",
            "api_auth_login": "auth_routes.login",
            "api_auth_logout": "auth_routes.logout",
            "normalize_role": "canonical_normalize_role",
            "has_permission": "canonical_has_permission",
        }
        for name, canonical_symbol in expected_calls.items():
            source = ast.unparse(functions[name])
            self.assertIn(canonical_symbol, source, name)

        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        for live_route in ("api_auth_me", "api_auth_login", "api_auth_logout"):
            self.assertNotIn(f"def {live_route}():\n    return _legacy", app_source)

    def test_exam_adapter_has_no_independent_business_logic(self):
        source = (ROOT / "exam_integrity.py").read_text(encoding="utf-8")
        self.assertIn("from teacher_app.exams.routes import register_legacy_exam_routes", source)
        self.assertIn("return register_legacy_exam_routes(base)", source)
        self.assertNotIn("@app.", source)

    def test_pgy_atomic_actions_delegate_to_canonical_service(self):
        source = (ROOT / "pgy_atomic.py").read_text(encoding="utf-8")
        self.assertIn("from teacher_app.pgy import service as pgy_service", source)
        for action in (
            "submit_assignment",
            "teacher_sign_assignment",
            "group_countersign_assignment",
            "finalize_assignment",
            "reopen_assignment",
            "cancel_assignment",
        ):
            self.assertIn(f"pgy_service.{action}", source)

    def test_production_entrypoint_stays_composition_only(self):
        source = (ROOT / "pgy_app.py").read_text(encoding="utf-8")
        self.assertIn("import app as legacy_app", source)
        self.assertIn("app = register_rbac_681(legacy_app)", source)
        self.assertIn("app = register_sensitive_elevation_69(legacy_app)", source)
        self.assertNotIn("@app.", source)
        self.assertNotIn("CREATE TABLE", source)

    def test_frontend_assets_have_static_as_the_only_canonical_location(self):
        static = ROOT / "static"
        mirror_names = {
            path.name for path in static.iterdir() if path.is_file() and path.suffix in {".css", ".html", ".js"}
        }
        root_mirrors = {path.name for path in ROOT.iterdir() if path.is_file()} & mirror_names
        self.assertEqual(root_mirrors, set())

        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('STATIC_DIR = BASE_DIR / "static"', app_source)
        for route in ("index.html", "area-internal.html", "area-pgy.html", "login.html", "system.html"):
            self.assertIn(f'send_from_directory(STATIC_DIR, "{route}")', app_source)


if __name__ == "__main__":
    unittest.main()
