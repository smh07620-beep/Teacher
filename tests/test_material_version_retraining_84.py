import contextlib
import sqlite3
import unittest
from unittest.mock import patch

import release_contract
import schema_migrations
from teacher_app.common import db as common_db
from teacher_app.learning import schema as learning_schema
from teacher_app.learning import versioning
from teacher_app.learning import progress_service
from teacher_app.maintenance.material_version_migration import material_version_retraining_84
from teacher_app.materials import repository as material_repository
from teacher_app.materials import schema as material_schema


def material_entry(material_id="mat-1"):
    return {
        "id": material_id,
        "filename": "AG158.pdf",
        "title": "AG158 水質監測 SOP",
        "description": "",
        "category": "",
        "group_key": "grpBio",
        "training_area": "internal",
        "course_id": "",
        "folder": material_id,
        "page_count": 10,
        "date_added": "2026-09-25 12:00",
        "storage_filename": "AG158.pdf",
        "storage_backend": "local",
        "storage_key": "",
        "slides_prefix": "",
        "storage_meta": "{}",
        "material_type": "sop",
        "atlas_meta": "{}",
        "active": 1,
    }


class MaterialVersionRetraining84Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        material_schema.init_schema(self.conn, "sqlite")
        learning_schema.init_schema(self.conn, "sqlite")
        self.conn.execute(
            "CREATE TABLE learning_progress ("
            "material_id TEXT NOT NULL,username TEXT NOT NULL,position TEXT NOT NULL DEFAULT '{}',"
            "progress REAL NOT NULL DEFAULT 0,completed INTEGER NOT NULL DEFAULT 0,"
            "updated_at TEXT NOT NULL DEFAULT '',PRIMARY KEY(material_id,username))"
        )
        material_repository.insert_material_on_connection(
            self.conn,
            "sqlite",
            material_entry(),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    @contextlib.contextmanager
    def _read(self):
        yield self.conn, "sqlite"

    @contextlib.contextmanager
    def _tx(self):
        try:
            yield self.conn, "sqlite"
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def test_release_contract_registers_0084_once(self):
        versions = [version for version, _fn in schema_migrations.MIGRATIONS]
        self.assertEqual(versions.count("0084-material-version-retraining"), 1)
        self.assertLess(
            release_contract.REQUIRED_MIGRATIONS.index("0084-material-version-retraining"),
            release_contract.REQUIRED_MIGRATIONS.index("0086-notification-read-state"),
        )

    def test_migration_is_idempotent_and_backfills_version_one(self):
        material_version_retraining_84(self.conn, "sqlite")
        material_version_retraining_84(self.conn, "sqlite")
        material_cols = {
            row[1] for row in self.conn.execute("PRAGMA table_info(materials)").fetchall()
        }
        progress_cols = {
            row[1] for row in self.conn.execute("PRAGMA table_info(material_progress)").fetchall()
        }
        smart_cols = {
            row[1] for row in self.conn.execute("PRAGMA table_info(learning_progress)").fetchall()
        }
        self.assertTrue(
            {"current_version", "required_completion_version", "version_updated_at", "version_updated_by"}
            <= material_cols
        )
        self.assertIn("completed_version", progress_cols)
        self.assertIn("completed_version", smart_cols)
        rows = self.conn.execute(
            "SELECT version,requires_retraining FROM material_versions WHERE material_id='mat-1'"
        ).fetchall()
        self.assertEqual([(row["version"], row["requires_retraining"]) for row in rows], [(1, 0)])

    def test_minor_revision_preserves_completion_and_major_revision_requires_retraining(self):
        material_version_retraining_84(self.conn, "sqlite")
        with patch.object(common_db, "read_connection", self._read), patch.object(
            common_db, "transaction", self._tx
        ):
            minor = material_repository.publish_material_version(
                "mat-1",
                published_by="admin",
                change_reason="修正文句與排版",
                requires_retraining=False,
            )
            self.assertEqual(minor["currentVersion"], 2)
            self.assertEqual(minor["requiredCompletionVersion"], 1)
            self.assertTrue(versioning.completion_is_current(minor, 1))

            major = material_repository.publish_material_version(
                "mat-1",
                published_by="admin",
                change_reason="重大流程修訂",
                requires_retraining=True,
            )
            self.assertEqual(major["currentVersion"], 3)
            self.assertEqual(major["requiredCompletionVersion"], 3)
            self.assertFalse(versioning.completion_is_current(major, 1))
            self.assertTrue(versioning.completion_is_current(major, 3))
            history = material_repository.list_material_versions("mat-1")
            self.assertEqual([row["version"] for row in history], [3, 2, 1])
            self.assertTrue(history[0]["requiresRetraining"])

    def test_new_material_after_0084_gets_v1_history(self):
        material_version_retraining_84(self.conn, "sqlite")
        with patch.object(common_db, "read_connection", self._read), patch.object(
            common_db, "transaction", self._tx
        ):
            material_repository.insert_material(material_entry("mat-2"))
            rows = material_repository.list_material_versions("mat-2")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["version"], 1)
        self.assertEqual(rows[0]["changeReason"], "initial publication")

    def test_version_helper_separates_current_and_stale_completions(self):
        materials = [
            {"id": "minor", "currentVersion": 2, "requiredCompletionVersion": 1},
            {"id": "major", "currentVersion": 3, "requiredCompletionVersion": 3},
        ]
        valid, stale = versioning.valid_completed_material_ids(
            materials,
            [
                {"material_id": "minor", "completed_version": 1},
                {"material_id": "major", "completed_version": 1},
            ],
        )
        self.assertEqual(valid, {"minor"})
        self.assertEqual(stale, {"major"})

    def test_manual_completion_snapshots_current_material_version(self):
        material_version_retraining_84(self.conn, "sqlite")
        with patch.object(common_db, "read_connection", self._read), patch.object(
            common_db, "transaction", self._tx
        ), patch.object(
            progress_service.material_repository,
            "get_material",
            return_value={
                "id": "mat-1",
                "active": True,
                "area": "internal",
                "group": "grpBio",
                "currentVersion": 4,
                "requiredCompletionVersion": 4,
            },
        ):
            progress_service.mark_material_complete(
                {
                    "username": "student.bio",
                    "name": "Bio Student",
                    "empId": "E100",
                    "role": "student",
                    "preferredArea": "internal",
                    "preferredGroup": "grpBio",
                },
                "mat-1",
            )
        row = self.conn.execute(
            "SELECT completed_version FROM material_progress WHERE emp_id=? AND material_id=?",
            ("E100", "mat-1"),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["completed_version"], 4)

    def test_material_version_history_survives_catalog_record_deletion(self):
        material_version_retraining_84(self.conn, "sqlite")
        with patch.object(common_db, "read_connection", self._read), patch.object(
            common_db, "transaction", self._tx
        ):
            material_repository.publish_material_version(
                "mat-1",
                published_by="admin",
                change_reason="重大 SOP 修訂",
                requires_retraining=True,
            )
            material_repository.delete_material_record("mat-1")
        rows = self.conn.execute(
            "SELECT version,change_reason FROM material_versions WHERE material_id=? ORDER BY version",
            ("mat-1",),
        ).fetchall()
        self.assertEqual([row["version"] for row in rows], [1, 2])
        self.assertEqual(rows[-1]["change_reason"], "重大 SOP 修訂")


if __name__ == "__main__":
    unittest.main()
