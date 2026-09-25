import sqlite3
import unittest

import release_contract
import schema_migrations
from teacher_app.maintenance.material_version_migration import material_version_retraining_84
from teacher_app.materials import repository, versioning


class MaterialVersionRetraining84Tests(unittest.TestCase):
    def _db(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE materials (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                group_key TEXT NOT NULL DEFAULT 'grpBio',
                training_area TEXT NOT NULL DEFAULT 'internal',
                course_id TEXT NOT NULL DEFAULT '',
                folder TEXT NOT NULL,
                page_count INTEGER NOT NULL DEFAULT 0,
                date_added TEXT NOT NULL,
                storage_filename TEXT NOT NULL,
                storage_backend TEXT NOT NULL DEFAULT 'local',
                storage_key TEXT NOT NULL DEFAULT '',
                slides_prefix TEXT NOT NULL DEFAULT '',
                storage_meta TEXT NOT NULL DEFAULT '{}',
                material_type TEXT NOT NULL DEFAULT 'standard',
                atlas_meta TEXT NOT NULL DEFAULT '{}',
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE material_progress (
                emp_id TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                material_id TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                PRIMARY KEY(emp_id,material_id)
            )
            """
        )
        conn.execute(
            "INSERT INTO materials "
            "(id,filename,title,folder,date_added,storage_filename,material_type) "
            "VALUES ('mat-1','sop.pdf','SOP','mat-1','2026-09-25','sop.pdf','sop')"
        )
        conn.execute(
            "INSERT INTO material_progress(emp_id,name,material_id,completed_at) "
            "VALUES ('E001','Learner','mat-1','2026-09-20T00:00:00+00:00')"
        )
        return conn

    def test_release_registry_ends_with_0084_once(self):
        versions = [version for version, _fn in schema_migrations.MIGRATIONS]
        self.assertEqual(versions.count("0084-material-version-retraining"), 1)
        self.assertEqual(release_contract.REQUIRED_MIGRATIONS[-1], "0084-material-version-retraining")

    def test_sqlite_migration_is_additive_and_idempotent(self):
        conn = self._db()
        try:
            material_version_retraining_84(conn, "sqlite")
            material_version_retraining_84(conn, "sqlite")
            material_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(materials)").fetchall()
            }
            progress_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(material_progress)").fetchall()
            }
            self.assertTrue({
                "current_version",
                "required_completion_version",
                "version_updated_at",
                "version_updated_by",
            }.issubset(material_columns))
            self.assertIn("completed_version", progress_columns)
            versions = conn.execute(
                "SELECT material_id,version,requires_retraining FROM material_versions"
            ).fetchall()
            self.assertEqual(len(versions), 1)
            self.assertEqual(dict(versions[0])["version"], 1)
            progress = conn.execute(
                "SELECT completed_version FROM material_progress WHERE emp_id='E001'"
            ).fetchone()
            self.assertEqual(dict(progress)["completed_version"], 1)
        finally:
            conn.close()

    def test_repository_projection_exposes_version_state(self):
        item = repository.material_row_to_dict({
            "id": "mat-1",
            "filename": "sop.pdf",
            "title": "SOP",
            "description": "",
            "date_added": "",
            "page_count": 0,
            "storage_filename": "sop.pdf",
            "storage_backend": "local",
            "storage_key": "",
            "slides_prefix": "",
            "storage_meta": "{}",
            "material_type": "sop",
            "atlas_meta": "{}",
            "current_version": 3,
            "required_completion_version": 2,
            "version_updated_at": "2026-09-25T00:00:00+00:00",
            "version_updated_by": "admin",
            "active": 1,
            "group_key": "grpBio",
            "training_area": "internal",
            "course_id": "",
        })
        self.assertEqual(item["currentVersion"], 3)
        self.assertEqual(item["requiredCompletionVersion"], 2)
        self.assertEqual(item["versionUpdatedBy"], "admin")

    def test_completion_must_meet_retraining_threshold(self):
        material = {"requiredCompletionVersion": 3}
        self.assertFalse(versioning.completion_is_current(material, 2))
        self.assertTrue(versioning.completion_is_current(material, 3))
        self.assertTrue(versioning.completion_is_current(material, 4))


if __name__ == "__main__":
    unittest.main()
