import ast
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
    def test_create_app_registers_error_handler_and_empty_blueprints(self):
        app = create_app()
        self.assertTrue(app.config["SECRET_KEY"])
        self.assertIn("teacher_auth", app.blueprints)
        self.assertIn("pgy", app.blueprints)
        self.assertIn("teacher_exams", app.blueprints)
        api_rules = [rule.rule for rule in app.url_map.iter_rules() if rule.rule.startswith("/api/")]
        self.assertTrue(api_rules)
        self.assertTrue(all(rule.startswith("/api/pgy/") for rule in api_rules))

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


class LegacyAppPyStillOwnsRoutes(unittest.TestCase):
    def test_app_py_still_defines_flask_app_and_db_conn(self):
        source = Path(__file__).parents[1].joinpath("app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        self.assertIn("_db_conn", names)
        self.assertIn("require_roles", names)
        self.assertTrue(any(isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "app" for t in node.targets) for node in tree.body))


if __name__ == "__main__":
    unittest.main()
