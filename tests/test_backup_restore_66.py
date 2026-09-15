import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import backup_restore
import schema_migrations


class DatabaseBase:
    def __init__(self, path):
        self.path = path

    def _db_conn(self):
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"


def create_65_tables(base):
    conn, _kind = base._db_conn()
    try:
        conn.execute(
            """
            CREATE TABLE user_accounts (
                username TEXT PRIMARY KEY,
                display_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'student'
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


class BackupRestore66Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        directory = Path(self.temp.name)
        self.source = DatabaseBase(directory / "legacy-backup.db")
        self.destination = DatabaseBase(directory / "upgraded.db")

    def test_65_backup_restores_to_0066_without_overwriting_live_rows(self):
        create_65_tables(self.source)
        source_conn, _kind = self.source._db_conn()
        try:
            source_conn.execute(
                "INSERT INTO user_accounts (username, display_name, role) VALUES (?, ?, ?)",
                ("teacher1", "Backup Teacher", "teacher"),
            )
            source_conn.execute(
                "INSERT INTO pgy_assignments (id, learner_username, teacher_username, status) VALUES (?, ?, ?, ?)",
                ("legacy-1", "student1", "teacher1", "submitted"),
            )
        finally:
            source_conn.close()
        payload = backup_restore.build_backup(self.source)

        create_65_tables(self.destination)
        schema_migrations.apply_migrations(self.destination)
        destination_conn, _kind = self.destination._db_conn()
        try:
            destination_conn.execute(
                "INSERT INTO user_accounts (username, display_name, role, roles_json) VALUES (?, ?, ?, ?)",
                ("teacher1", "Live Production Name", "teacher", '["clinical_teacher"]'),
            )
        finally:
            destination_conn.close()

        restored = backup_restore._restore(self.destination, payload)
        self.assertEqual(restored["user_accounts"], 0)
        self.assertEqual(restored["pgy_assignments"], 1)

        destination_conn, _kind = self.destination._db_conn()
        try:
            user = destination_conn.execute(
                "SELECT display_name, roles_json FROM user_accounts WHERE username='teacher1'"
            ).fetchone()
            assignment = destination_conn.execute(
                "SELECT status, sign_mode, first_signature, second_signature FROM pgy_assignments WHERE id='legacy-1'"
            ).fetchone()
        finally:
            destination_conn.close()

        self.assertEqual(user["display_name"], "Live Production Name")
        self.assertEqual(json.loads(user["roles_json"]), ["clinical_teacher"])
        self.assertEqual(assignment["status"], "submitted")
        self.assertEqual(assignment["sign_mode"], "legacy")
        self.assertEqual(assignment["first_signature"], "{}")
        self.assertEqual(assignment["second_signature"], "{}")


if __name__ == "__main__":
    unittest.main()
