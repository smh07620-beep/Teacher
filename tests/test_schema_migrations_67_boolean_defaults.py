import sqlite3
import tempfile
import unittest
from pathlib import Path

import schema_migrations


class RecordingResult:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class RecordingPostgresConnection:
    """Record generated PostgreSQL DDL while modelling additive column checks."""

    def __init__(self):
        self.calls = []
        self.tables = {"material_jobs", "media_processing_jobs"}
        self.columns = {
            "material_jobs": set(),
            "media_processing_jobs": set(),
        }

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        normalized = " ".join(sql.split()).lower()
        if "information_schema.tables" in normalized:
            return RecordingResult([{"present": 1}])
        if "information_schema.columns" in normalized:
            table = params[0]
            return RecordingResult(
                [{"column_name": column} for column in self.columns.get(table, set())]
            )
        if normalized.startswith("alter table"):
            table = normalized.split()[2]
            definition = normalized.split(" add column if not exists ", 1)[1]
            self.columns.setdefault(table, set()).add(definition.split()[0])
        return RecordingResult()

    def close(self):
        return None


class RecordingPostgresBase:
    def __init__(self, conn):
        self.conn = conn

    def _db_conn(self):
        return self.conn, "postgres"


class SqliteBase:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "migrations.sqlite"

    def close(self):
        self.temp.cleanup()

    def _db_conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def create_material_jobs(self):
        conn, _kind = self._db_conn()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS material_jobs (id TEXT PRIMARY KEY)")
        finally:
            conn.close()


class BooleanDefaultMigration67Tests(unittest.TestCase):
    def setUp(self):
        self.base = SqliteBase()
        self.addCleanup(self.base.close)

    def _postgres_sql(self):
        conn = RecordingPostgresConnection()
        schema_migrations._smart_learning_67(conn, "postgres")
        schema_migrations._b_free_local_worker_67(conn, "postgres")
        schema_migrations.ensure_r2_free_budget_guard_67(
            RecordingPostgresBase(conn)
        )
        return "\n".join(sql for sql, _params in conn.calls)

    def test_postgres_boolean_defaults_are_native_literals(self):
        sql = self._postgres_sql()
        self.assertNotRegex(sql, r"(?i)BOOLEAN[^,)]*DEFAULT\\s+0\\b")
        self.assertNotRegex(sql, r"(?i)BOOLEAN[^,)]*DEFAULT\\s+1\\b")
        self.assertIn("completed BOOLEAN NOT NULL DEFAULT FALSE", sql)
        self.assertIn("cleanup_pending BOOLEAN NOT NULL DEFAULT FALSE", sql)
        self.assertIn("is_staging BOOLEAN NOT NULL DEFAULT TRUE", sql)

    def test_sqlite_defaults_stay_integer_and_partial_reruns_are_safe(self):
        self.base.create_material_jobs()
        conn, kind = self.base._db_conn()
        try:
            # Simulate a crash after DDL but before the migration marker write.
            schema_migrations._smart_learning_67(conn, kind)
            schema_migrations._b_free_local_worker_67(conn, kind)
            schema_migrations._smart_learning_67(conn, kind)
            schema_migrations._b_free_local_worker_67(conn, kind)

            learning_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='learning_progress'"
            ).fetchone()["sql"]
            self.assertIn("completed INTEGER NOT NULL DEFAULT 0", learning_sql)
            material_columns = {
                row["name"]: row["dflt_value"]
                for row in conn.execute("PRAGMA table_info(material_jobs)").fetchall()
            }
            self.assertEqual(str(material_columns["cleanup_pending"]), "0")
        finally:
            conn.close()

        schema_migrations.ensure_r2_free_budget_guard_67(self.base)
        schema_migrations.ensure_r2_free_budget_guard_67(self.base)
        conn, _kind = self.base._db_conn()
        try:
            r2_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='r2_usage_ledger'"
            ).fetchone()["sql"]
        finally:
            conn.close()
        self.assertIn("is_staging INTEGER NOT NULL DEFAULT 1", r2_sql)

    def test_applied_0067_compatibility_ensure_and_registry_repeat_safely(self):
        self.base.create_material_jobs()
        conn, _kind = self.base._db_conn()
        try:
            conn.execute(
                "CREATE TABLE schema_migrations ("
                "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) "
                "VALUES ('0067-b-free-local-worker', 'already-applied')"
            )
        finally:
            conn.close()

        schema_migrations.ensure_r2_free_budget_guard_67(self.base)
        schema_migrations.ensure_r2_free_budget_guard_67(self.base)

        applied = schema_migrations.apply_migrations(self.base)
        self.assertIn("0067-smart-learning-content", applied)
        self.assertEqual(schema_migrations.apply_migrations(self.base), [])

        conn, _kind = self.base._db_conn()
        try:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()
        self.assertTrue(
            {"r2_upload_reservations", "r2_usage_ledger"}.issubset(tables)
        )


if __name__ == "__main__":
    unittest.main()
