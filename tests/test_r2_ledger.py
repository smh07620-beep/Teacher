import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.maintenance import migrations
from teacher_app.storage import r2_ledger


class R2LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.sqlite"

        conn, kind = self.connect()
        try:
            migrations._r2_free_budget_guard_67(conn, kind)
        finally:
            conn.close()

        self.db_patch = patch(
            "teacher_app.storage.r2_ledger.common_db.get_connection",
            side_effect=self.connect,
        )
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def row(self, key):
        conn, _ = self.connect()
        try:
            return dict(
                conn.execute(
                    "SELECT * FROM r2_usage_ledger WHERE object_key=?", (key,)
                ).fetchone()
            )
        finally:
            conn.close()

    def test_record_object_upserts_bytes_and_accumulates_operations(self):
        r2_ledger.record_object("materials/a", 10)
        first = self.row("materials/a")
        self.assertEqual(first["object_bytes"], 10)
        self.assertEqual(first["estimated_operations"], 1)
        self.assertEqual(first["deleted_at"], "")

        r2_ledger.record_object(
            "materials/a", 20, multipart_parts=3, estimated_operations=4
        )
        second = self.row("materials/a")
        self.assertEqual(second["object_bytes"], 20)
        self.assertEqual(second["multipart_parts"], 3)
        self.assertEqual(second["estimated_operations"], 5)
        self.assertEqual(second["deleted_at"], "")

    def test_staging_default_and_delete_accounting_match_historical_contract(self):
        r2_ledger.record_object("_staging/job", 30)
        row = self.row("_staging/job")
        self.assertEqual(row["is_staging"], 1)
        self.assertEqual(row["estimated_operations"], 1)

        r2_ledger.record_deleted("_staging/job")
        deleted = self.row("_staging/job")
        self.assertTrue(deleted["deleted_at"])
        self.assertEqual(deleted["estimated_operations"], 2)

        # Repeated delete does not keep incrementing an already deleted object.
        r2_ledger.record_deleted("_staging/job")
        self.assertEqual(self.row("_staging/job")["estimated_operations"], 2)


if __name__ == "__main__":
    unittest.main()
