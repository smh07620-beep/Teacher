import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from teacher_app.config import DATA_DIR
from teacher_app.maintenance import legacy_data_migrations
from teacher_app.materials import catalog


class SqliteConnectionFactory:
    def __init__(self, path: Path):
        self.path = path

    def __call__(self):
        conn = sqlite3.connect(str(self.path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"


class LegacyDataMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.factory = SqliteConnectionFactory(self.root / "migration.db")
        self._create_quiz_schema()

    def tearDown(self):
        self.tempdir.cleanup()

    def _create_quiz_schema(self):
        conn, _kind = self.factory()
        try:
            conn.execute(
                """
                CREATE TABLE quiz_categories (
                    id TEXT PRIMARY KEY,
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    training_area TEXT NOT NULL DEFAULT 'internal',
                    course_id TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    draw_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE quiz_questions (
                    id TEXT PRIMARY KEY,
                    quiz_category_id TEXT NOT NULL,
                    tag TEXT NOT NULL DEFAULT '',
                    question TEXT NOT NULL,
                    question_type TEXT NOT NULL DEFAULT 'choice',
                    image_url TEXT NOT NULL DEFAULT '',
                    options TEXT NOT NULL,
                    correct INTEGER NOT NULL DEFAULT 0,
                    explanation TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
        finally:
            conn.close()

    def _fetchone(self, sql, params=()):
        conn, _kind = self.factory()
        try:
            return conn.execute(sql, params).fetchone()
        finally:
            conn.close()

    def _fetchall(self, sql, params=()):
        conn, _kind = self.factory()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def test_fresh_seed_uses_canonical_data_path_and_v540_runs_after_seed(self):
        self.assertEqual(
            legacy_data_migrations.BUILTIN_QUIZ_SEED_PATH,
            DATA_DIR / "builtin_quiz_seed.json",
        )

        legacy_data_migrations.run_legacy_data_migrations(self.factory)

        categories = self._fetchall(
            "SELECT id,group_key,training_area,draw_count FROM quiz_categories ORDER BY sort_order"
        )
        questions = self._fetchall("SELECT id FROM quiz_questions")
        markers = {
            row["meta_key"]: row["meta_value"]
            for row in self._fetchall("SELECT meta_key,meta_value FROM app_meta")
        }
        self.assertEqual([row["id"] for row in categories], ["subA1", "subA2", "subA3", "zoneB"])
        self.assertTrue(all(row["group_key"] == "grpBio" for row in categories))
        self.assertTrue(all(row["training_area"] == "internal" for row in categories))
        self.assertTrue(all(row["draw_count"] == 10 for row in categories))
        self.assertEqual(len(questions), 40)
        self.assertTrue(markers[legacy_data_migrations.BIO_QUIZ_MIGRATION_KEY])
        self.assertTrue(markers[legacy_data_migrations.V540_EXAM_SETTINGS_MIGRATION_KEY])

    def test_seed_is_idempotent_and_completed_marker_prevents_resurrection(self):
        legacy_data_migrations.seed_builtin_bio_quizzes(self.factory)
        marker_before = self._fetchone(
            "SELECT meta_value FROM app_meta WHERE meta_key=?",
            (legacy_data_migrations.BIO_QUIZ_MIGRATION_KEY,),
        )["meta_value"]
        counts_before = (
            self._fetchone("SELECT COUNT(*) AS count FROM quiz_categories")["count"],
            self._fetchone("SELECT COUNT(*) AS count FROM quiz_questions")["count"],
        )

        legacy_data_migrations.seed_builtin_bio_quizzes(self.factory)

        self.assertEqual(
            counts_before,
            (
                self._fetchone("SELECT COUNT(*) AS count FROM quiz_categories")["count"],
                self._fetchone("SELECT COUNT(*) AS count FROM quiz_questions")["count"],
            ),
        )
        marker_after = self._fetchone(
            "SELECT meta_value FROM app_meta WHERE meta_key=?",
            (legacy_data_migrations.BIO_QUIZ_MIGRATION_KEY,),
        )["meta_value"]
        self.assertEqual(marker_before, marker_after)

        conn, _kind = self.factory()
        try:
            conn.execute("DELETE FROM quiz_questions WHERE quiz_category_id=?", ("subA1",))
            conn.execute("DELETE FROM quiz_categories WHERE id=?", ("subA1",))
        finally:
            conn.close()

        legacy_data_migrations.seed_builtin_bio_quizzes(self.factory)

        self.assertIsNone(
            self._fetchone("SELECT id FROM quiz_categories WHERE id=?", ("subA1",))
        )
        self.assertEqual(
            self._fetchone(
                "SELECT COUNT(*) AS count FROM quiz_questions WHERE quiz_category_id=?",
                ("subA1",),
            )["count"],
            0,
        )

    def test_v540_marker_makes_draw_count_migration_one_time(self):
        conn, _kind = self.factory()
        try:
            conn.execute(
                "INSERT INTO quiz_categories "
                "(id,group_key,training_area,course_id,title,description,sort_order,date_added,active,draw_count) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("existing", "grpBio", "internal", "", "Existing", "", 0, "", 1, 0),
            )
        finally:
            conn.close()

        legacy_data_migrations.migrate_v540_exam_settings(self.factory)
        self.assertEqual(
            self._fetchone("SELECT draw_count FROM quiz_categories WHERE id='existing'")["draw_count"],
            10,
        )

        conn, _kind = self.factory()
        try:
            conn.execute("UPDATE quiz_categories SET draw_count=0 WHERE id='existing'")
            conn.execute(
                "INSERT INTO quiz_categories "
                "(id,group_key,training_area,course_id,title,description,sort_order,date_added,active,draw_count) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("new", "grpBio", "internal", "", "New", "", 1, "", 1, 0),
            )
        finally:
            conn.close()

        legacy_data_migrations.migrate_v540_exam_settings(self.factory)
        values = {
            row["id"]: row["draw_count"]
            for row in self._fetchall(
                "SELECT id,draw_count FROM quiz_categories WHERE id IN ('existing','new')"
            )
        }
        self.assertEqual(values, {"existing": 0, "new": 0})

    def test_missing_or_corrupt_seed_is_best_effort_and_unmarked(self):
        missing = self.root / "missing.json"
        legacy_data_migrations.seed_builtin_bio_quizzes(self.factory, seed_path=missing)
        self.assertIsNone(
            self._fetchone(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='app_meta'"
            )
        )

        conn, _kind = self.factory()
        try:
            conn.execute(
                "INSERT INTO quiz_categories "
                "(id,group_key,training_area,course_id,title,description,sort_order,date_added,active,draw_count) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("existing", "grpBio", "internal", "", "Existing", "", 0, "", 1, 0),
            )
        finally:
            conn.close()
        legacy_data_migrations.run_legacy_data_migrations(
            self.factory,
            seed_path=missing,
        )
        self.assertEqual(
            self._fetchone("SELECT draw_count FROM quiz_categories WHERE id='existing'")["draw_count"],
            10,
        )
        self.assertIsNone(
            self._fetchone(
                "SELECT meta_value FROM app_meta WHERE meta_key=?",
                (legacy_data_migrations.BIO_QUIZ_MIGRATION_KEY,),
            )
        )
        self.assertIsNotNone(
            self._fetchone(
                "SELECT meta_value FROM app_meta WHERE meta_key=?",
                (legacy_data_migrations.V540_EXAM_SETTINGS_MIGRATION_KEY,),
            )
        )

        corrupt = self.root / "corrupt.json"
        corrupt.write_text("{ definitely-not-json", encoding="utf-8")
        with self.assertLogs(legacy_data_migrations.__name__, level="WARNING"):
            legacy_data_migrations.seed_builtin_bio_quizzes(
                self.factory,
                seed_path=corrupt,
            )
        self.assertIsNone(
            self._fetchone(
                "SELECT meta_value FROM app_meta WHERE meta_key=?",
                (legacy_data_migrations.BIO_QUIZ_MIGRATION_KEY,),
            )
        )

    def test_builtin_material_meta_is_optional_and_noop_does_not_create_it(self):
        missing_meta = self.root / "slides_meta.json"
        with mock.patch.object(catalog, "META_FILE", missing_meta):
            self.assertEqual(catalog.load_builtin_meta(), [])
            legacy_data_migrations.init_builtin_meta()
            self.assertFalse(missing_meta.exists())


if __name__ == "__main__":
    unittest.main()
