import hashlib
import io
import json
import sqlite3
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

from flask import Flask

import backup_restore


class MaintenanceApiIntegrationTests(
    unittest.TestCase
):
    def setUp(self):
        self.temp = (
            tempfile.TemporaryDirectory()
        )
        self.addCleanup(
            self.temp.cleanup
        )

        self.db_path = (
            Path(self.temp.name)
            / "maintenance.db"
        )

        self.base = (
            types.SimpleNamespace()
        )

        self.base.app = Flask(
            __name__
        )

        self.base.app.config.update(
            TESTING=True,
            SECRET_KEY="maintenance-test",
        )

        self.base.user = {
            "username": "admin1",
            "role": "education_admin",
        }

        self.base._current_user = (
            lambda: self.base.user
        )

        self.base.normalize_role = (
            lambda value:
            str(value or "student")
        )

        self.base._db_conn = (
            self.connect
        )

        conn, _kind = self.connect()

        try:
            conn.execute(
                """
                CREATE TABLE user_accounts
                (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                INSERT INTO user_accounts
                (
                    id,
                    username,
                    display_name
                )
                VALUES
                (
                    1,
                    'admin1',
                    'Original Name'
                )
                """
            )
        finally:
            conn.close()

        backup_restore.register_backup_restore(
            self.base
        )

        self.client = (
            self.base.app.test_client()
        )

    def connect(self):
        conn = sqlite3.connect(
            str(self.db_path)
        )

        conn.row_factory = (
            sqlite3.Row
        )

        conn.isolation_level = None

        return conn, "sqlite"

    @staticmethod
    def read_payload(zip_bytes):
        with zipfile.ZipFile(
            io.BytesIO(zip_bytes),
            "r",
        ) as zf:
            return json.loads(
                zf.read(
                    "teacher-backup.json"
                ).decode("utf-8")
            )

    @staticmethod
    def expected_sha(payload):
        unsigned = dict(payload)
        unsigned.pop(
            "sha256",
            None,
        )

        raw = json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode("utf-8")

        return hashlib.sha256(
            raw
        ).hexdigest()

    def test_backup_zip_manifest_and_sha256(self):
        response = self.client.get(
            "/api/maintenance/backup"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTrue(
            response.content_type.startswith(
                "application/zip"
            )
        )

        payload = self.read_payload(
            response.data
        )

        self.assertEqual(
            payload["format"],
            backup_restore.BACKUP_FORMAT,
        )

        expected_version = (
            Path(__file__)
            .parents[1]
            .joinpath("VERSION")
            .read_text(encoding="utf-8")
            .strip()
        )

        self.assertEqual(
            payload["version"],
            expected_version,
        )

        self.assertEqual(
            payload["sha256"],
            self.expected_sha(
                payload
            ),
        )

        self.assertIn(
            "user_accounts",
            payload["tables"],
        )

    def test_tampered_backup_is_rejected(self):
        original = self.client.get(
            "/api/maintenance/backup"
        )

        payload = self.read_payload(
            original.data
        )

        payload[
            "tables"
        ][
            "user_accounts"
        ][0][
            "display_name"
        ] = "TAMPERED"

        # Keep the old SHA intentionally.
        tampered_zip = (
            backup_restore._zip_payload(
                payload
            )
        )

        response = self.client.post(
            "/api/maintenance/restore",
            data={
                "confirm": "RESTORE",
                "file": (
                    io.BytesIO(
                        tampered_zip
                    ),
                    "backup.zip",
                ),
            },
            content_type=(
                "multipart/form-data"
            ),
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertIn(
            "SHA256",
            response.get_json()[
                "error"
            ],
        )

    def test_restore_does_not_overwrite_existing_row(self):
        backup_zip = (
            self.client.get(
                "/api/maintenance/backup"
            ).data
        )

        conn, _kind = (
            self.connect()
        )

        try:
            conn.execute(
                """
                UPDATE user_accounts
                SET display_name=
                    'Live Production Name'
                WHERE id=1
                """
            )
        finally:
            conn.close()

        response = self.client.post(
            "/api/maintenance/restore",
            data={
                "confirm": "RESTORE",
                "file": (
                    io.BytesIO(
                        backup_zip
                    ),
                    "backup.zip",
                ),
            },
            content_type=(
                "multipart/form-data"
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
            response.get_data(
                as_text=True
            ),
        )

        conn, _kind = (
            self.connect()
        )

        try:
            row = conn.execute(
                """
                SELECT display_name
                FROM user_accounts
                WHERE id=1
                """
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(
            row["display_name"],
            "Live Production Name",
        )

    def test_auditor_cannot_download_backup(self):
        self.base.user = {
            "username": "audit1",
            "role": "auditor",
        }

        response = self.client.get(
            "/api/maintenance/backup"
        )

        self.assertEqual(
            response.status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
