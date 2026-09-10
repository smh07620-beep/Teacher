import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import schema_migrations


class Migration66Base:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "migration66.db"

    def close(self):
        self.temp.cleanup()

    def _db_conn(self):
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def create_65_schema(self, *, existing_roles_json=False):
        conn, _kind = self._db_conn()
        try:
            roles_json = ", roles_json TEXT NOT NULL DEFAULT '[]'" if existing_roles_json else ""
            conn.execute(
                f"""
                CREATE TABLE user_accounts (
                    username TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL DEFAULT '',
                    emp_id TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'student'
                    {roles_json}
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE pgy_assignments (
                    id TEXT PRIMARY KEY,
                    learner_username TEXT NOT NULL,
                    teacher_username TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'assigned'
                )
                """
            )
        finally:
            conn.close()


class RecordingResult:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class RecordingPostgresConnection:
    """Enough of psycopg's mapping-row interface to validate the SQL path."""

    def __init__(self):
        self.calls = []
        self.columns = {
            "user_accounts": {"username", "role"},
            "pgy_assignments": {"id"},
        }

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        normalized = " ".join(sql.split()).lower()
        if "information_schema.tables" in normalized:
            return RecordingResult([{"present": 1}])
        if "information_schema.columns" in normalized:
            table = params[0]
            return RecordingResult(
                [{"column_name": column} for column in self.columns[table]]
            )
        if normalized.startswith("alter table"):
            table = normalized.split()[2]
            for column in ("roles_json", "sign_mode", "first_signature", "second_signature"):
                if column in normalized:
                    self.columns[table].add(column)
                    break
        if normalized.startswith("select username, role, roles_json"):
            return RecordingResult()
        return RecordingResult()


class SchemaMigration66Tests(unittest.TestCase):
    def setUp(self):
        self.base = Migration66Base()
        self.addCleanup(self.base.close)

    def test_registry_includes_single_0066_migration(self):
        versions = [version for version, _fn in schema_migrations.MIGRATIONS]
        self.assertIn("0066-additive-rbac-pgy-signing", versions)
        self.assertEqual(len(versions), len(set(versions)))

    def test_sqlite_upgrade_preserves_legacy_rows_and_is_idempotent(self):
        self.base.create_65_schema()
        conn, _kind = self.base._db_conn()
        try:
            conn.execute(
                "INSERT INTO user_accounts (username, display_name, emp_id, role) VALUES (?, ?, ?, ?)",
                ("teacher1", "Legacy Teacher", "T001", "teacher"),
            )
            conn.execute(
                "INSERT INTO pgy_assignments (id, learner_username, teacher_username, status) VALUES (?, ?, ?, ?)",
                ("legacy-1", "student1", "teacher1", "submitted"),
            )
        finally:
            conn.close()

        applied = schema_migrations.apply_migrations(self.base)
        self.assertIn("0066-additive-rbac-pgy-signing", applied)
        self.assertEqual(schema_migrations.apply_migrations(self.base), [])

        conn, _kind = self.base._db_conn()
        try:
            user = conn.execute("SELECT role, roles_json FROM user_accounts WHERE username='teacher1'").fetchone()
            assignment = conn.execute(
                "SELECT status, sign_mode, first_signature, second_signature FROM pgy_assignments WHERE id='legacy-1'"
            ).fetchone()
            versions = conn.execute("SELECT version FROM schema_migrations").fetchall()
        finally:
            conn.close()

        self.assertEqual(user["role"], "teacher")
        self.assertEqual(json.loads(user["roles_json"]), ["clinical_teacher"])
        self.assertEqual(assignment["status"], "submitted")
        self.assertEqual(assignment["sign_mode"], "legacy")
        self.assertEqual(assignment["first_signature"], "{}")
        self.assertEqual(assignment["second_signature"], "{}")
        self.assertEqual(
            [row["version"] for row in versions].count("0066-additive-rbac-pgy-signing"),
            1,
        )

    def test_existing_multi_role_data_is_not_overwritten(self):
        self.base.create_65_schema(existing_roles_json=True)
        conn, _kind = self.base._db_conn()
        try:
            conn.execute(
                "INSERT INTO user_accounts (username, role, roles_json) VALUES (?, ?, ?)",
                ("teacher1", "teacher", '["clinical_teacher","group_leader"]'),
            )
        finally:
            conn.close()

        schema_migrations.apply_migrations(self.base)

        conn, _kind = self.base._db_conn()
        try:
            row = conn.execute("SELECT roles_json FROM user_accounts WHERE username='teacher1'").fetchone()
        finally:
            conn.close()
        self.assertEqual(json.loads(row["roles_json"]), ["clinical_teacher", "group_leader"])

    def test_postgres_path_uses_native_additive_ddl_and_placeholders(self):
        conn = RecordingPostgresConnection()
        schema_migrations._additive_rbac_pgy_signing_66(conn, "postgres")

        ddl = [sql for sql, _params in conn.calls if "ALTER TABLE" in sql]
        self.assertEqual(len(ddl), 4)
        self.assertTrue(all("ADD COLUMN IF NOT EXISTS" in sql for sql in ddl))
        self.assertEqual(
            conn.columns["user_accounts"],
            {"username", "role", "roles_json"},
        )
        self.assertTrue(
            {"sign_mode", "first_signature", "second_signature"}
            <= conn.columns["pgy_assignments"]
        )
        self.assertTrue(
            all("?" not in sql for sql, params in conn.calls if params)
        )


if __name__ == "__main__":
    unittest.main()
