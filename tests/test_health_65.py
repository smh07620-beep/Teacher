import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

import health_65
import schema_migrations


ROOT = Path(__file__).parents[1]


class HealthBase:
    def __init__(self):
        self.temp = (
            tempfile.TemporaryDirectory()
        )

        self.path = (
            Path(self.temp.name)
            / "health65.db"
        )

        self.app = Flask(
            f"health65-{id(self)}"
        )

        self.app.config.update(
            TESTING=True
        )

    def close(self):
        self.temp.cleanup()

    def _db_conn(self):
        conn = sqlite3.connect(
            str(self.path)
        )

        conn.row_factory = sqlite3.Row
        conn.isolation_level = None

        return conn, "sqlite"


class Health65Tests(
    unittest.TestCase
):
    def test_healthy_when_database_and_migrations_are_ready(self):
        base = HealthBase()
        self.addCleanup(base.close)

        schema_migrations.apply_migrations(
            base
        )

        health_65.register_health(
            base
        )

        response = (
            base.app
            .test_client()
            .get("/health")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        body = response.get_json()

        self.assertTrue(
            body["ok"]
        )

        self.assertEqual(
            body["status"],
            "healthy",
        )

        expected_version = (
            ROOT.joinpath("VERSION")
            .read_text(encoding="utf-8")
            .strip()
        )

        self.assertEqual(
            body["version"],
            expected_version,
        )

        self.assertTrue(
            body["database"]["ok"]
        )

        self.assertEqual(
            body["database"]["kind"],
            "sqlite",
        )

        self.assertTrue(
            body["migrations"]["ok"]
        )

        self.assertEqual(
            body["migrations"]["missing"],
            [],
        )

    def test_missing_0065_returns_degraded_503(self):
        base = HealthBase()
        self.addCleanup(base.close)

        schema_migrations.ensure_registry(
            base
        )

        conn, _kind = (
            base._db_conn()
        )

        try:
            conn.execute(
                """
                INSERT INTO schema_migrations
                (version, applied_at)
                VALUES (?, ?)
                """,
                (
                    "0064-baseline",
                    "2026-09-09T00:00:00+00:00",
                ),
            )
        finally:
            conn.close()

        health_65.register_health(
            base
        )

        response = (
            base.app
            .test_client()
            .get("/health")
        )

        self.assertEqual(
            response.status_code,
            503,
        )

        body = response.get_json()

        self.assertFalse(
            body["ok"]
        )

        self.assertEqual(
            body["status"],
            "degraded",
        )

        self.assertIn(
            "0065-architecture",
            body["migrations"]["missing"],
        )

    def test_database_failure_does_not_leak_exception_or_secret(self):
        class BrokenBase:
            def __init__(self):
                self.app = Flask(
                    f"broken-health-{id(self)}"
                )

                self.app.config.update(
                    TESTING=True
                )

            def _db_conn(self):
                raise RuntimeError(
                    "postgres://user:"
                    "super-secret-password@"
                    "secret-db-host/"
                    "production"
                )

        base = BrokenBase()

        health_65.register_health(
            base
        )

        response = (
            base.app
            .test_client()
            .get("/health")
        )

        self.assertEqual(
            response.status_code,
            503,
        )

        body = response.get_json()

        serialized = json.dumps(
            body,
            ensure_ascii=False,
        )

        self.assertFalse(
            body["ok"]
        )

        self.assertEqual(
            body["database"]["kind"],
            "unavailable",
        )

        self.assertNotIn(
            "super-secret-password",
            serialized,
        )

        self.assertNotIn(
            "secret-db-host",
            serialized,
        )

        self.assertNotIn(
            "postgres://",
            serialized,
        )

    def test_existing_legacy_health_route_is_replaced(self):
        base = HealthBase()
        self.addCleanup(base.close)

        @base.app.get("/health")
        def legacy_health():
            return {
                "legacy": True
            }

        schema_migrations.apply_migrations(
            base
        )

        health_65.register_health(
            base
        )

        response = (
            base.app
            .test_client()
            .get("/health")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        body = response.get_json()

        self.assertNotIn(
            "legacy",
            body,
        )

        self.assertEqual(
            body["status"],
            "healthy",
        )


if __name__ == "__main__":
    unittest.main()
