import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

import schema_migrations
from teacher_app.auth import rbac_legacy_adapter


class DatabaseRuntimeConvergenceTests(unittest.TestCase):
    def test_schema_registration_uses_registry_without_r2_compatibility_ddl(self):
        base = SimpleNamespace(app=Flask("migration-registration-test"))
        with patch.object(
            schema_migrations,
            "apply_migrations",
            return_value=["0067-r2-free-budget-guard"],
        ) as apply_migrations, patch.object(
            schema_migrations,
            "ensure_r2_free_budget_guard_67",
            side_effect=AssertionError("compatibility DDL must not run at startup"),
        ) as compatibility_ensure:
            app = schema_migrations.register_schema_migrations(base)

        self.assertIs(app, base.app)
        # App-shaped/owner-shaped registration without an explicit DB seam uses
        # the canonical common.db connection rather than treating the owner as a
        # database dependency bag.
        apply_migrations.assert_called_once_with(None)
        compatibility_ensure.assert_not_called()
        self.assertTrue(app.extensions["teacher_schema_migrations_registered"])

    def test_rbac_registration_does_not_promote_historical_account(self):
        base = SimpleNamespace(
            app=Flask("rbac-registration-test"),
            require_admin=lambda: None,
            _current_user=lambda: None,
        )
        with patch.object(
            rbac_legacy_adapter.account_roles,
            "grant_system_admin",
            side_effect=AssertionError("role maintenance must be explicit"),
        ) as grant_system_admin:
            rbac_legacy_adapter.register_legacy_rbac(base)

        grant_system_admin.assert_not_called()


if __name__ == "__main__":
    unittest.main()
