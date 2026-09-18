import os
import tempfile
import unittest
from pathlib import Path

from teacher_app import create_app
from teacher_app.common.audit import build_audit_event
from teacher_app.common.auth import (
    CANONICAL_ROLES,
    has_permission,
    normalize_role,
    require_permission,
    require_role,
)
from teacher_app.common.db import execute, fetch_one, placeholder, transaction
from teacher_app.common.errors import ApiError, error_body
from tests.test_rbac_roles import RBAC


class ApplicationFactoryTests(unittest.TestCase):
    def test_create_app_registers_error_handler_and_modular_blueprints(self):
        app = create_app()
        self.assertTrue(app.config["SECRET_KEY"])
        self.assertIn("teacher_auth", app.blueprints)
        self.assertIn("pgy", app.blueprints)
        self.assertIn("teacher_exams", app.blueprints)
        api_rules = [rule.rule for rule in app.url_map.iter_rules() if rule.rule.startswith("/api/")]
        self.assertTrue(api_rules)
        self.assertTrue(any(rule.startswith("/api/pgy/") for rule in api_rules))
        self.assertIn("/api/exam-attempts", api_rules)

    def test_api_error_uses_legacy_compatible_payload(self):
        app = create_app()

        @app.get("/__m1/error")
        def boom():
            raise ApiError("ASSIGNMENT_NOT_FOUND", "找不到指派。", status=404)

        client = app.test_client()
        response = client.get("/__m1/error")
        self.assertEqual(response.status_code, 404)
        payload = response.get_json()
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["error"], "找不到指派。")
        self.assertEqual(payload["errorDetail"]["code"], "ASSIGNMENT_NOT_FOUND")
        self.assertEqual(payload["errorDetail"]["message"], "找不到指派。")

    def test_factory_composition_has_no_legacy_host_adapter(self):
        source = Path(__file__).parents[1].joinpath("teacher_app", "factory.py").read_text(encoding="utf-8")
        self.assertNotIn("legacy_host", source)
        self.assertNotIn("LegacyBaseAdapter", source)
        self.assertNotIn("runtime_from_owner", source)
        self.assertIn("build_canonical_question_runtime", source)

    def test_fresh_factories_expose_the_same_route_set(self):
        first = create_app()
        second = create_app()
        first_routes = {(rule.rule, rule.endpoint, tuple(sorted(rule.methods or ()))) for rule in first.url_map.iter_rules()}
        second_routes = {(rule.rule, rule.endpoint, tuple(sorted(rule.methods or ()))) for rule in second.url_map.iter_rules()}
        self.assertEqual(first_routes, second_routes)
        self.assertGreater(len(first_routes), 0)


class CommonAuthTests(unittest.TestCase):
    def test_matches_legacy_app_py_rbac_definitions(self):
        self.assertEqual(CANONICAL_ROLES, RBAC["CANONICAL_ROLES"])
        self.assertEqual(normalize_role("learner"), RBAC["normalize_role"]("learner"))
        self.assertEqual(normalize_role("teacher"), "clinical_teacher")
        self.assertFalse(has_permission({"role": "system_admin"}, "evaluation.sign"))
        self.assertFalse(has_permission({"role": "education_admin"}, "evaluation.sign"))
        self.assertTrue(has_permission({"role": "clinical_teacher"}, "evaluation.sign"))

    def test_require_role_and_permission(self):
        teacher = {"role": "clinical_teacher", "username": "t1"}
        self.assertEqual(require_role(teacher, "clinical_teacher")["username"], "t1")
        with self.assertRaises(ApiError) as forbidden:
            require_role({"role": "system_admin"}, "clinical_teacher")
        self.assertEqual(forbidden.exception.status, 403)
        with self.assertRaises(ApiError) as unsigned:
            require_permission({"role": "system_admin"}, "evaluation.sign")
        self.assertEqual(unsigned.exception.status, 403)
        with self.assertRaises(ApiError) as anonymous:
            require_role(None, "student")
        self.assertEqual(anonymous.exception.status, 401)
        self.assertIn("loginRequired", error_body("LOGIN_REQUIRED", "請先登入後再執行此操作。", {"loginRequired": True}))


class CommonDbTests(unittest.TestCase):
    def test_sqlite_transaction_commits_and_rolls_back(self):
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        previous = os.environ.get("TEACHER_SQLITE_PATH")
        os.environ.pop("DATABASE_URL", None)
        os.environ["TEACHER_SQLITE_PATH"] = path
        try:
            self.assertEqual(placeholder("sqlite"), "?")
            self.assertEqual(placeholder("postgres"), "%s")
            with transaction() as (conn, kind):
                self.assertEqual(kind, "sqlite")
                execute(conn, "CREATE TABLE m1_probe (id INTEGER PRIMARY KEY, name TEXT)")
                execute(conn, "INSERT INTO m1_probe(name) VALUES (?)", ("ok",))
            with transaction() as (conn, _kind):
                row = fetch_one(conn, "SELECT name FROM m1_probe WHERE name = ?", ("ok",))
                self.assertEqual(row["name"], "ok")
            with self.assertRaises(RuntimeError):
                with transaction() as (conn, _kind):
                    execute(conn, "INSERT INTO m1_probe(name) VALUES (?)", ("fail",))
                    raise RuntimeError("boom")
            with transaction() as (conn, _kind):
                missing = fetch_one(conn, "SELECT name FROM m1_probe WHERE name = ?", ("fail",))
                self.assertIsNone(missing)
        finally:
            if previous is None:
                os.environ.pop("TEACHER_SQLITE_PATH", None)
            else:
                os.environ["TEACHER_SQLITE_PATH"] = previous
            Path(path).unlink(missing_ok=True)


class AuditHelperTests(unittest.TestCase):
    def test_audit_event_includes_transition_fields(self):
        event = build_audit_event(
            assignment_id="a1",
            actor_username="stu",
            action="submit",
            from_status="assigned",
            to_status="submitted",
        )
        self.assertEqual(event["assignment_id"], "a1")
        self.assertEqual(event["action"], "submit")
        self.assertTrue(event["created_at"])


class RootCompatibilitySurfaceTests(unittest.TestCase):
    def test_app_py_is_only_a_legacy_host_alias(self):
        source = Path(__file__).parents[1].joinpath("app.py").read_text(encoding="utf-8")
        self.assertIn("from teacher_app import legacy_host as _legacy_host", source)
        self.assertIn("sys.modules[__name__] = _legacy_host", source)
        self.assertNotIn("def _db_conn", source)
        self.assertNotIn("Flask(", source)


if __name__ == "__main__":
    unittest.main()
