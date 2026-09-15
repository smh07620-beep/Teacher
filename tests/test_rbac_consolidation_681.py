"""Behavioural regression coverage for the 6.8.1 RBAC/profile hotfix."""
import json
import sqlite3
import tempfile
from unittest.mock import patch
import unittest
from pathlib import Path

import health_65
import schema_migrations
from rbac_681 import _ensure_07620
from teacher_app.auth.service import public_user
from teacher_app.common.auth import has_permission


class _Base:
    DEFAULT_GROUP = "grpBio"
    DEFAULT_TRAINING_AREA = "internal"

    def __init__(self, path):
        self.path = path

    def _db_conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    @staticmethod
    def normalize_group(value):
        return value or "grpBio"

    @staticmethod
    def normalize_area(value):
        return value or "internal"


class ProfileMigration681Tests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        handle.close()
        self.path = handle.name
        self.base = _Base(self.path)
        conn, _ = self.base._db_conn()
        conn.execute("CREATE TABLE user_accounts (username TEXT PRIMARY KEY,password_hash TEXT NOT NULL,display_name TEXT NOT NULL,emp_id TEXT NOT NULL,role TEXT NOT NULL,roles_json TEXT NOT NULL DEFAULT '[]',preferred_area TEXT NOT NULL DEFAULT 'internal',preferred_group TEXT NOT NULL DEFAULT 'grpBio',active INTEGER NOT NULL DEFAULT 1,session_version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL DEFAULT '',last_login_at TEXT NOT NULL DEFAULT '')")
        conn.execute("INSERT INTO user_accounts(username,password_hash,display_name,emp_id,role,roles_json) VALUES(?,?,?,?,?,?)", ("staff", "unchanged-hash", "評雪誠", "07620", "clinical_teacher", '["clinical_teacher"]'))
        conn.commit()
        conn.close()

    def tearDown(self):
        Path(self.path).unlink(missing_ok=True)

    def test_0069_is_additive_idempotent_and_preserves_security_columns(self):
        schema_migrations.apply_migrations(self.base)
        schema_migrations.apply_migrations(self.base)
        conn, _ = self.base._db_conn()
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(user_accounts)").fetchall()}
        row = dict(conn.execute("SELECT * FROM user_accounts WHERE username='staff'").fetchone())
        migrations = {row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        conn.close()
        self.assertIn("0069-user-profile-titles", migrations)
        self.assertEqual(columns["professional_title"][4], "''")
        self.assertEqual(columns["responsibility_tags"][4], "'[]'")
        self.assertEqual(row["professional_title"], "")
        self.assertEqual(row["responsibility_tags"], "[]")
        self.assertEqual(row["roles_json"], '["clinical_teacher"]')
        self.assertEqual(row["password_hash"], "unchanged-hash")

    def test_titles_and_tags_are_presentation_only(self):
        self.assertFalse(has_permission({"role": "student", "professionalTitle": "系統管理員", "responsibilityTags": ["組長"]}, "system.manage"))
        self.assertFalse(has_permission({"role": "student", "professionalTitle": "組長"}, "exam.publish"))

    def test_profile_serialization_is_safe_and_keeps_roles_separate(self):
        user = public_user(self.base, {"username": "staff", "display_name": "評雪誠", "emp_id": "07620", "role": "student", "roles_json": '["student"]', "professional_title": "系統管理員", "responsibility_tags": '["品管","POCT"]'}, include_roles=True)
        self.assertEqual(user["professionalTitle"], "系統管理員")
        self.assertEqual(user["responsibilityTags"], ["品管", "POCT"])
        self.assertEqual(user["roles"], ["student"])

    def test_health_contract_requires_0069(self):
        self.assertIn("0069-user-profile-titles", health_65.REQUIRED_MIGRATIONS)

    def test_0069_uses_portable_text_json_columns_for_postgres_and_sqlite(self):
        with patch.object(schema_migrations, "_add_columns") as add:
            schema_migrations._user_profile_titles_69(object(), "postgres")
        self.assertEqual(add.call_args.args[1], "postgres")
        self.assertEqual(add.call_args.args[3], {
            "professional_title": "professional_title TEXT NOT NULL DEFAULT ''",
            "responsibility_tags": "responsibility_tags TEXT NOT NULL DEFAULT '[]'",
        })

    def test_07620_role_ensure_preserves_roles_and_password_hash(self):
        conn, _ = self.base._db_conn()
        conn.execute("INSERT INTO user_accounts(username,password_hash,display_name,emp_id,role,roles_json) VALUES(?,?,?,?,?,?)", ("07620", "unchanged-admin-hash", "評雪誠", "07620-admin", "clinical_teacher", '["clinical_teacher","auditor"]'))
        conn.close()
        self.assertTrue(_ensure_07620(self.base))
        conn, _ = self.base._db_conn()
        user = dict(conn.execute("SELECT role,roles_json,password_hash FROM user_accounts WHERE username='07620'").fetchone())
        conn.close()
        self.assertEqual(user["role"], "system_admin")
        self.assertEqual(json.loads(user["roles_json"]), ["system_admin", "clinical_teacher", "auditor"])
        self.assertEqual(user["password_hash"], "unchanged-admin-hash")


class WorkspaceContract681Tests(unittest.TestCase):
    def test_normal_ui_does_not_prompt_or_persist_admin_key(self):
        source = Path(__file__).parents[1].joinpath("static", "system-admin.js").read_text(encoding="utf-8")
        self.assertNotIn("/api/admin/elevation", source)
        self.assertIn("return 'rbac-session'", source)

    def test_learner_office_guard_is_server_side(self):
        source = Path(__file__).parents[1].joinpath("rbac_681.py").read_text(encoding="utf-8")
        self.assertIn("OFFICE_EXTENSIONS", source)
        self.assertIn("previewRequired", source)
        self.assertIn("return jsonify({\"error\": \"教材預覽尚未完成", source)


if __name__ == "__main__":
    unittest.main()
