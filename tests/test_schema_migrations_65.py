import sqlite3
import tempfile
import unittest
from pathlib import Path

import schema_migrations


class Migration65Base:
    def __init__(self):
        self.temp = (
            tempfile.TemporaryDirectory()
        )
        self.path = (
            Path(self.temp.name)
            / "migration65.db"
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


class SchemaMigration65Tests(
    unittest.TestCase
):
    def setUp(self):
        self.base = Migration65Base()

    def tearDown(self):
        self.base.close()

    def test_registry_contains_0064_and_0065_once(self):
        versions = [
            version
            for version, _fn
            in schema_migrations.MIGRATIONS
        ]

        self.assertIn(
            "0064-baseline",
            versions,
        )

        self.assertIn(
            "0065-architecture",
            versions,
        )

        self.assertEqual(
            len(versions),
            len(set(versions)),
        )

    def test_apply_migrations_is_idempotent(self):
        first = schema_migrations.apply_migrations(
            self.base
        )

        self.assertIn(
            "0064-baseline",
            first,
        )

        self.assertIn(
            "0065-architecture",
            first,
        )

        second = schema_migrations.apply_migrations(
            self.base
        )

        self.assertEqual(
            second,
            [],
        )

        conn, _kind = (
            self.base._db_conn()
        )

        try:
            rows = conn.execute(
                """
                SELECT version
                FROM schema_migrations
                ORDER BY version
                """
            ).fetchall()
        finally:
            conn.close()

        versions = [
            row["version"]
            for row in rows
        ]

        self.assertEqual(
            versions.count(
                "0064-baseline"
            ),
            1,
        )

        self.assertEqual(
            versions.count(
                "0065-architecture"
            ),
            1,
        )

    def test_0065_marker_does_not_destroy_existing_data(self):
        conn, _kind = (
            self.base._db_conn()
        )

        try:
            conn.execute(
                """
                CREATE TABLE production_sentinel
                (
                    id INTEGER PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                INSERT INTO production_sentinel
                (id, value)
                VALUES (1, 'keep-me')
                """
            )
        finally:
            conn.close()

        schema_migrations.apply_migrations(
            self.base
        )

        schema_migrations.apply_migrations(
            self.base
        )

        conn, _kind = (
            self.base._db_conn()
        )

        try:
            row = conn.execute(
                """
                SELECT value
                FROM production_sentinel
                WHERE id=1
                """
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(
            row["value"],
            "keep-me",
        )


if __name__ == "__main__":
    unittest.main()
