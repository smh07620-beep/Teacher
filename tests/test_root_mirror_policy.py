"""Regression policy for root compatibility cleanup.

Structural checks protect compatibility seams while preventing business logic
from drifting back into root adapters after a canonical domain has converged.
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
        document = ROOT.joinpath("ARCHITECTURE.md").read_text(encoding="utf-8")
        for marker in (
            "pgy_app:app",
            "teacher_app.auth.service",
            "teacher_app.common.auth",
            "teacher_app.exams",
            "teacher_app.pgy.service",
            "teacher_app.materials.service",
            "teacher_app.courses.service",
            "teacher_app.assessments.service",
            "Converged read/data ownership",
            "Converged data/rule ownership",
            "teacher_app.materials.external_media_routes",
            "teacher_app.storage.providers",
            "teacher_app.worker.repository",
            "teacher_app.worker.routes",
            "Frozen / converged",
            "professional_title",
            "responsibility_tags",
        ):
            self.assertIn(marker, document)
        self.assertNotIn("data-access migration continues where still required", document)

    def test_root_compatibility_inventory_is_explicit_and_bounded(self):
        document = ROOT.joinpath("ARCHITECTURE.md").read_text(encoding="utf-8")
        compatibility = {
            "admin_elevation_68.py",
            "ai_privacy.py",
            "app.py",
            "atlas_70.py",
            "backup_restore.py",
            "course_bundle_72.py",
            "course_bundle_followup_73.py",
            "exam_integrity.py",
            "external_media_68.py",
            "free_worker_67.py",
            "health_65.py",
            "legacy_office_69.py",
            "media_processing_67.py",
            "multi_role_66.py",
            "pgy_frontend.py",
            "pgy_signing_66.py",
            "pgy_workflow.py",
            "production_hardening.py",
            "question_bank_68.py",
            "rbac_681.py",
            "schema_migrations.py",
            "sensitive_elevation_69.py",
            "smart_learning_67.py",
            "upload_hardening.py",
        }
        for marker in (
            "### Retained root compatibility inventory",
            *(f"`{name}`" for name in sorted(compatibility)),
            "`teacher_app.compatibility`",
            "`legacy_app.py`",
            "`legacy_routes.py`",
            "`teacher_app.maintenance.migrations`",
            "`teacher_app.auth.elevation`",
            "`teacher_app.atlas.routes`",
            "Production `teacher_app.factory.create_app()` imports canonical package owners directly",
        ):
            self.assertIn(marker, document)
        root_python = {path.name for path in ROOT.glob("*.py")}
        canonical_root = {"pgy_app.py", "material_worker.py", "ai_question_worker.py", "release_contract.py"}
        self.assertEqual(root_python - compatibility - canonical_root, set())
        factory = ROOT.joinpath("teacher_app/factory.py").read_text(encoding="utf-8")
        self.assertNotIn("teacher_app.compatibility", factory)
        self.assertNotIn("load_legacy_app", factory)

    def test_live_auth_routes_are_thin_canonical_delegates_without_duplicate_legacy_impls(self):
        functions = module_functions(ROOT / "teacher_app" / "legacy_host.py")
        expected_calls = {
            "api_auth_me": "auth_routes.me",
            "api_auth_login": "auth_routes.login",
            "api_auth_logout": "auth_routes.logout",
            "normalize_role": "canonical_normalize_role",
            "has_permission": "canonical_has_permission",
            "_normalize_username": "auth_service.normalize_username",
            "_user_public": "auth_service.public_user",
            "_current_user": "auth_service.current_user",
        }
        for name, canonical_symbol in expected_calls.items():
            source = ast.unparse(functions[name])
            self.assertIn(canonical_symbol, source, name)

        retired = {
            "_legacy_normalize_role",
            "_legacy_has_permission",
            "_legacy_normalize_username",
            "_legacy_user_public",
            "_legacy_current_user",
            "_legacy_require_roles",
            "_legacy_api_auth_me",
            "_legacy_api_auth_login",
            "_legacy_api_auth_logout",
        }
        self.assertFalse(retired & set(functions), sorted(retired & set(functions)))

    def test_exam_adapter_has_no_independent_business_logic(self):
        source = (ROOT / "exam_integrity.py").read_text(encoding="utf-8")
        self.assertIn("from teacher_app.exams.routes import register_legacy_exam_routes", source)
        self.assertIn("return register_legacy_exam_routes(base)", source)
        self.assertNotIn("@app.", source)

    def test_pgy_controller_is_thin_canonical_service_adapter(self):
        adapter = (ROOT / "pgy_workflow.py").read_text(encoding="utf-8")
        source = (ROOT / "teacher_app" / "pgy" / "routes_legacy.py").read_text(encoding="utf-8")
        self.assertIn("teacher_app.pgy", adapter)
        self.assertNotIn("@app.", adapter)
        self.assertIn("from teacher_app.pgy import repository as pgy_repo", source)
        self.assertIn("from teacher_app.pgy import service as pgy_service", source)
        self.assertIn("pgy_repo.init_schema(conn, kind)", source)
        for call in (
            "workflow_meta",
            "list_assignment_candidates",
            "list_assignments",
            "get_assignment",
            "create_assignment",
            "update_assignment",
            "submit_assignment",
            "teacher_sign_assignment",
            "group_countersign_assignment",
            "finalize_assignment",
            "reopen_assignment",
            "cancel_assignment",
            "list_audit",
        ):
            self.assertIn(f"pgy_service.{call}", source)
        for legacy_sql in (
            "CREATE TABLE IF NOT EXISTS pgy_assignments",
            "INSERT INTO pgy_assignments",
            "UPDATE pgy_assignments SET",
            "SELECT username,display_name,emp_id,role,preferred_group,active FROM user_accounts",
        ):
            self.assertNotIn(legacy_sql, source)
        self.assertIn("_assignment_dict = pgy_repo.assignment_dict", source)
        self.assertIn("pgy_repo.write_audit", source)
        self.assertIn("def _legacy_error_body", source)

    def test_redundant_pgy_atomic_patch_layer_is_retired(self):
        self.assertFalse((ROOT / "pgy_atomic.py").exists())
        entrypoint = (ROOT / "pgy_app.py").read_text(encoding="utf-8")
        factory = (ROOT / "teacher_app" / "factory.py").read_text(encoding="utf-8")
        self.assertNotIn("register_pgy_atomic_workflow", entrypoint + factory)
        self.assertNotIn("from pgy_atomic import", entrypoint + factory)
        self.assertIn("from teacher_app import create_app", entrypoint)
        self.assertIn("app = create_app()", entrypoint)

    def test_production_entrypoint_stays_composition_only(self):
        source = (ROOT / "pgy_app.py").read_text(encoding="utf-8")
        factory = (ROOT / "teacher_app" / "factory.py").read_text(encoding="utf-8")
        self.assertIn("from teacher_app import create_app", source)
        self.assertIn("app = create_app()", source)
        self.assertNotIn("legacy_app", source)
        self.assertNotIn("legacy_host", factory)
        self.assertIn("app = register_rbac_681(app)", factory)
        self.assertIn("app = register_sensitive_elevation(app)", factory)
        for name in (
            "register_legacy_material_routes",
            "register_legacy_course_routes",
            "register_legacy_assessment_routes",
            "register_assessment_performance_712",
            "register_pgy_atomic_workflow",
        ):
            self.assertNotIn(name, source)
        self.assertNotIn("@app.", source)
        self.assertNotIn("CREATE TABLE", source)

    def test_frontend_assets_have_static_as_the_only_canonical_location(self):
        static = ROOT / "static"
        mirror_names = {
            path.name for path in static.iterdir() if path.is_file() and path.suffix in {".css", ".html", ".js"}
        }
        root_mirrors = {path.name for path in ROOT.iterdir() if path.is_file()} & mirror_names
        self.assertEqual(root_mirrors, set())

        config_source = (ROOT / "teacher_app" / "config.py").read_text(encoding="utf-8")
        page_source = (ROOT / "teacher_app" / "frontend" / "pages.py").read_text(encoding="utf-8")
        self.assertIn('STATIC_DIR = BASE_DIR / "static"', config_source)
        for route in ("index.html", "area-internal.html", "area-pgy.html", "login.html", "system.html"):
            self.assertIn(f'send_from_directory(static_dir, "{route}")', page_source)


if __name__ == "__main__":
    unittest.main()
