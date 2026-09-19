import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask, g

from teacher_app.auth import rbac_legacy_adapter, rbac_routes


class RbacRoutesBaseFreeTests(unittest.TestCase):
    def test_direct_flask_registration_owns_profile_and_guards(self):
        app = Flask("rbac-direct-app")
        app.config.update(TESTING=True, SECRET_KEY="rbac-test")

        @app.before_request
        def bind_user():
            g.teacher_user = {
                "username": "admin",
                "role": "system_admin",
                "roles": ["system_admin"],
                "preferredGroup": "grpBio",
            }

        with patch.object(
            rbac_legacy_adapter,
            "register_legacy_rbac",
            side_effect=AssertionError("direct Flask production path must not mutate a compatibility owner"),
        ), patch.object(
            rbac_routes.auth_repository,
            "find_user",
            return_value={"username": "admin"},
        ), patch.object(
            rbac_routes,
            "public_user",
            return_value={"username": "admin", "role": "system_admin"},
        ):
            registered = rbac_routes.register_rbac_681(app)
            response = app.test_client().get("/api/auth/profile")

        self.assertIs(registered, app)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "authenticated": True,
                "user": {"username": "admin", "role": "system_admin"},
            },
        )
        guards = app.extensions["teacher_rbac_guards"]
        self.assertEqual(
            set(guards),
            {
                "require_admin",
                "require_permission",
                "require_any_permission",
                "require_system_admin",
                "require_teacher_workspace",
                "require_scoped_permission",
            },
        )
        with app.test_request_context("/probe"):
            g.teacher_user = {
                "username": "admin",
                "role": "system_admin",
                "roles": ["system_admin"],
                "preferredGroup": "grpBio",
            }
            self.assertIsNone(guards["require_permission"]("course.manage"))
            self.assertIsNone(guards["require_system_admin"]())
            self.assertIsNone(guards["require_teacher_workspace"]())

    def test_direct_flask_guard_keeps_login_contract(self):
        app = Flask("rbac-direct-anonymous")
        rbac_routes.register_rbac_681(app)
        guards = app.extensions["teacher_rbac_guards"]

        with app.test_request_context("/api/courses"):
            denied = guards["require_permission"]("course.manage")

        response, status = denied
        self.assertEqual(status, 401)
        self.assertEqual(
            response.get_json(),
            {"error": "請先登入。", "loginRequired": True},
        )

    def test_legacy_owner_shape_remains_an_explicit_compatibility_path(self):
        app = Flask("rbac-compat-owner")
        owner = SimpleNamespace(app=app)

        with patch.object(
            rbac_legacy_adapter,
            "register_legacy_rbac",
            side_effect=AssertionError("compatibility owner should receive app-owned guards only"),
        ):
            registered = rbac_routes.register_rbac_681(owner)

        self.assertIs(registered, app)
        for name in (
            "require_admin",
            "require_permission",
            "require_any_permission",
            "require_system_admin",
            "require_teacher_workspace",
            "require_scoped_permission",
        ):
            self.assertTrue(callable(getattr(owner, name)))
        self.assertIn("teacher_rbac_guards", app.extensions)
        self.assertIn("current_profile", app.view_functions)

    def test_registration_order_stays_compat_then_scope_then_system_page(self):
        app = Flask("rbac-order")
        owner = SimpleNamespace(app=app)
        calls = []

        with patch.object(
            rbac_routes,
            "_install_compat_owner_guards",
            side_effect=lambda compat, _guards: calls.append(("compat", compat)),
        ), patch.object(
            rbac_routes.scope_filter,
            "register_scope_filter",
            side_effect=lambda flask_app: calls.append(("scope", flask_app)),
        ), patch.object(
            rbac_routes.system_page,
            "register_system_page",
            side_effect=lambda flask_app: calls.append(("system", flask_app)),
        ):
            rbac_routes.register_rbac_681(owner)

        self.assertEqual([name for name, _value in calls], ["compat", "scope", "system"])
        self.assertIs(calls[0][1], owner)
        self.assertIs(calls[1][1], app)
        self.assertIs(calls[2][1], app)

    def test_late_compat_owner_can_reuse_registered_app_guards_without_reregistering_hooks(self):
        app = Flask("rbac-late-compat")
        rbac_routes.register_rbac_681(app)
        owner = SimpleNamespace(app=app)

        with patch.object(
            rbac_routes.scope_filter,
            "register_scope_filter",
            side_effect=AssertionError("registered app must not install scope filter twice"),
        ), patch.object(
            rbac_routes.system_page,
            "register_system_page",
            side_effect=AssertionError("registered app must not install system page twice"),
        ):
            registered = rbac_routes.register_rbac_681(app, compat_owner=owner)

        self.assertIs(registered, app)
        self.assertIs(owner.require_permission, app.extensions["teacher_rbac_guards"]["require_permission"])

    def test_registration_is_idempotent_and_endpoint_policy_is_unchanged(self):
        app = Flask("rbac-idempotent")
        with patch.object(
            rbac_routes.scope_filter,
            "register_scope_filter",
            wraps=rbac_routes.scope_filter.register_scope_filter,
        ) as scope_register, patch.object(
            rbac_routes.system_page,
            "register_system_page",
            wraps=rbac_routes.system_page.register_system_page,
        ) as system_register:
            rbac_routes.register_rbac_681(app)
            rbac_routes.register_rbac_681(app)

        profile_rules = [
            rule
            for rule in app.url_map.iter_rules()
            if rule.rule == "/api/auth/profile" and "GET" in rule.methods
        ]
        self.assertEqual(len(profile_rules), 1)
        scope_register.assert_called_once_with(app)
        system_register.assert_called_once_with(app)
        self.assertIs(rbac_routes.LEGACY_ENDPOINT_POLICIES, rbac_legacy_adapter.LEGACY_ENDPOINT_POLICIES)
        self.assertEqual(
            rbac_routes.LEGACY_ENDPOINT_POLICIES["api_enqueue_material_job"],
            ("material.manage", "scoped"),
        )


if __name__ == "__main__":
    unittest.main()
