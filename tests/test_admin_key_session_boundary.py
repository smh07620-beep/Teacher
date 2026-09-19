import os
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

from teacher_app.assessments import runtime_question_routes
from teacher_app.auth import account_routes, elevation, rbac_legacy_adapter
from teacher_app.exams import record_routes
from teacher_app.maintenance import announcement_routes
from teacher_app.materials import template_routes
from teacher_app.pgy import assessment_routes
from teacher_app.storage import admin_routes


SYSTEM_ADMIN = {
    "username": "root",
    "role": "system_admin",
    "roles": ["system_admin"],
    "preferredGroup": "grpBio",
}


class AdminKeySessionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(f"admin-key-boundary-{id(self)}")
        self.app.config.update(TESTING=True, SECRET_KEY="admin-key-boundary-test")

    @staticmethod
    def _status(denied):
        return denied[1] if denied is not None else None

    def test_matching_header_cannot_authorize_anonymous_admin_guards(self):
        guards = (
            ("records", lambda: record_routes._require_admin(self.app)),
            ("announcements", lambda: announcement_routes._require_admin(self.app)),
            ("storage", lambda: admin_routes._require_admin(self.app)),
            ("document-templates", lambda: template_routes._require_admin(self.app)),
            ("pgy-templates", assessment_routes._require_admin),
            ("runtime-question-strict", lambda: runtime_question_routes._strict_admin(self.app)),
            ("rbac-compat", lambda: rbac_legacy_adapter.require_admin(self.app)),
        )
        with patch.dict(os.environ, {"ADMIN_KEY": "compat-secret"}, clear=False):
            for name, guard in guards:
                with self.subTest(guard=name), self.app.test_request_context(
                    "/probe",
                    headers={"X-Admin-Key": "compat-secret"},
                ):
                    g.teacher_user = None
                    self.assertEqual(self._status(guard()), 401)

    def test_valid_system_admin_session_authorizes_admin_guards_without_header(self):
        guards = (
            ("records", lambda: record_routes._require_admin(self.app)),
            ("announcements", lambda: announcement_routes._require_admin(self.app)),
            ("storage", lambda: admin_routes._require_admin(self.app)),
            ("document-templates", lambda: template_routes._require_admin(self.app)),
            ("pgy-templates", assessment_routes._require_admin),
            ("runtime-question-strict", lambda: runtime_question_routes._strict_admin(self.app)),
            ("rbac-compat", lambda: rbac_legacy_adapter.require_admin(self.app)),
        )
        for name, guard in guards:
            with self.subTest(guard=name), self.app.test_request_context("/probe"):
                g.teacher_user = SYSTEM_ADMIN
                self.assertIsNone(guard())

    def test_matching_header_cannot_upgrade_insufficient_session_role(self):
        guards = (
            ("records", lambda: record_routes._require_admin(self.app)),
            ("announcements", lambda: announcement_routes._require_admin(self.app)),
            ("storage", lambda: admin_routes._require_admin(self.app)),
            ("document-templates", lambda: template_routes._require_admin(self.app)),
            ("pgy-templates", assessment_routes._require_admin),
            ("runtime-question-strict", lambda: runtime_question_routes._strict_admin(self.app)),
            ("rbac-compat", lambda: rbac_legacy_adapter.require_admin(self.app)),
        )
        student = {
            "username": "student",
            "role": "student",
            "roles": ["student"],
            "preferredGroup": "grpBio",
        }
        with patch.dict(os.environ, {"ADMIN_KEY": "compat-secret"}, clear=False):
            for name, guard in guards:
                with self.subTest(guard=name), self.app.test_request_context(
                    "/probe",
                    headers={"X-Admin-Key": "compat-secret"},
                ):
                    g.teacher_user = student
                    self.assertEqual(self._status(guard()), 403)

    def test_unknown_compat_endpoint_header_does_not_upgrade_non_admin_session(self):
        teacher = {
            "username": "teacher",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredGroup": "grpBio",
        }
        with patch.dict(os.environ, {"ADMIN_KEY": "compat-secret"}, clear=False), self.app.test_request_context(
            "/probe",
            headers={"X-Admin-Key": "compat-secret"},
        ):
            g.teacher_user = teacher
            self.assertFalse(rbac_legacy_adapter.admin_key_override(self.app))

    def test_account_admin_guard_ignores_matching_header_for_insufficient_role(self):
        student = {
            "username": "student",
            "role": "student",
            "roles": ["student"],
            "preferredGroup": "grpBio",
        }
        self.app.extensions["teacher_rbac_681_registered"] = True
        with patch.dict(os.environ, {"ADMIN_KEY": "compat-secret"}, clear=False), self.app.test_request_context(
            "/api/users",
            headers={"X-Admin-Key": "compat-secret"},
        ):
            g.teacher_user = student
            self.assertEqual(self._status(account_routes._require_user_manage(self.app)), 403)

    def test_admin_elevation_secret_requires_authenticated_eligible_session(self):
        actor = {"user": None}
        elevation.register_admin_elevation(self.app, current_user=lambda: actor["user"])
        client = self.app.test_client()
        with patch.dict(os.environ, {"ADMIN_KEY": "elevation-secret"}, clear=False):
            anonymous = client.post("/api/admin/elevation", json={"password": "elevation-secret"})
            self.assertEqual(anonymous.status_code, 401)

            actor["user"] = {"username": "student", "role": "student", "roles": ["student"]}
            insufficient = client.post("/api/admin/elevation", json={"password": "elevation-secret"})
            self.assertEqual(insufficient.status_code, 403)

            actor["user"] = SYSTEM_ADMIN
            with patch.object(elevation, "store_elevation") as stored:
                allowed = client.post("/api/admin/elevation", json={"password": "elevation-secret"})
            self.assertEqual(allowed.status_code, 200)
            self.assertTrue(allowed.get_json()["ok"])
            stored.assert_called_once()

    def test_matching_header_never_overrides_question_group_scope(self):
        self.app.add_url_rule(
            "/question",
            endpoint="api_create_quiz_question",
            view_func=lambda: "ok",
        )
        teacher = {
            "username": "teacher",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredGroup": "grpBio",
        }
        with patch.dict(os.environ, {"ADMIN_KEY": "compat-secret"}, clear=False):
            with self.app.test_request_context(
                "/question?group=grpHema",
                headers={"X-Admin-Key": "compat-secret"},
            ):
                g.teacher_user = teacher
                self.assertFalse(rbac_legacy_adapter.admin_key_override(self.app))
                denied = runtime_question_routes._question_guard(self.app, scoped=True)
                self.assertEqual(self._status(denied), 403)

            with self.app.test_request_context(
                "/question?group=grpBio",
                headers={"X-Admin-Key": "compat-secret"},
            ):
                g.teacher_user = teacher
                self.assertTrue(rbac_legacy_adapter.admin_key_override(self.app))
                self.assertIsNone(runtime_question_routes._question_guard(self.app, scoped=True))

    def test_domain_route_sources_do_not_read_admin_header_directly(self):
        modules = (
            record_routes,
            runtime_question_routes,
            assessment_routes,
            announcement_routes,
            admin_routes,
            template_routes,
        )
        for module in modules:
            with self.subTest(module=module.__name__):
                source = Path(module.__file__).read_text(encoding="utf-8")
                self.assertNotIn("X-Admin-Key", source)

    def test_backend_admin_header_read_has_one_safe_canonical_owner(self):
        package_root = Path(rbac_legacy_adapter.__file__).resolve().parents[1]
        owners = sorted(
            str(path.relative_to(package_root)).replace("\\", "/")
            for path in package_root.rglob("*.py")
            if "X-Admin-Key" in path.read_text(encoding="utf-8")
        )
        self.assertEqual(owners, ["auth/rbac_legacy_adapter.py"])


if __name__ == "__main__":
    unittest.main()
