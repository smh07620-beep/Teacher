import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app import legacy_host
from teacher_app.factory import create_app


LEGACY_BOOTSTRAP_NAMES = (
    "init_exam_db",
    "init_materials_db",
    "init_quiz_db",
    "init_material_jobs_db",
    "init_learning_db",
    "init_announcements_db",
    "init_teaching_plan_db",
    "seed_builtin_bio_quizzes",
    "migrate_v540_exam_settings",
    "init_builtin_meta",
    "init_doc_templates_db",
    "init_pgy_assessment_db",
)


class FactoryFreshBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fresh.sqlite"

    def connect(self):
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def test_fresh_factory_bootstraps_without_legacy_schema_or_seed_helpers(self):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("legacy bootstrap helper must not be called")

        patches = [
            patch.object(legacy_host, name, side_effect=forbidden)
            for name in LEGACY_BOOTSTRAP_NAMES
            if hasattr(legacy_host, name)
        ]
        db_patch = patch("teacher_app.common.db.get_connection", side_effect=self.connect)
        db_patch.start()
        self.addCleanup(db_patch.stop)
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

        app = create_app()
        self.assertTrue(app.extensions.get("teacher_bootstrap_completed"))
        self.assertTrue(app.extensions.get("teacher_schema_migrations_registered"))

        conn, _kind = self.connect()
        try:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            signing_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(pgy_assignments)").fetchall()
            }
            migration_versions = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }
            data_markers = {
                row["meta_key"]
                for row in conn.execute("SELECT meta_key FROM app_meta").fetchall()
            }
            builtins = conn.execute(
                "SELECT COUNT(*) AS count FROM quiz_categories "
                "WHERE id IN ('subA1','subA2','subA3','zoneB')"
            ).fetchone()["count"]
            questions = conn.execute(
                "SELECT COUNT(*) AS count FROM quiz_questions "
                "WHERE quiz_category_id IN ('subA1','subA2','subA3','zoneB')"
            ).fetchone()["count"]
        finally:
            conn.close()

        self.assertTrue(
            {
                "user_accounts",
                "exam_records",
                "exam_attempts",
                "materials",
                "quiz_categories",
                "quiz_questions",
                "material_jobs",
                "courses",
                "material_progress",
                "announcements",
                "pgy_assignments",
                "doc_templates",
                "pgy_assessments",
            }.issubset(tables)
        )
        self.assertTrue(
            {"sign_mode", "teacher_signature", "group_signature", "final_confirmation"}.issubset(
                signing_columns
            )
        )
        self.assertIn("0066-additive-rbac-pgy-signing", migration_versions)
        self.assertTrue(
            {"v5.3.7-bio-quiz-migrated", "v5.4.0-exam-settings-migrated"}.issubset(
                data_markers
            )
        )
        self.assertEqual(builtins, 4)
        self.assertEqual(questions, 40)
        self.assertEqual(
            sum(
                1
                for view in app.view_functions.values()
                if getattr(view, "__module__", "") == "teacher_app.legacy_host"
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
