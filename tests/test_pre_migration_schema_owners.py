import sqlite3
import tempfile
import unittest
from pathlib import Path

from teacher_app.assessments import schema as assessment_schema
from teacher_app.courses import schema as course_schema
from teacher_app.exams import schema as exam_schema
from teacher_app.learning import schema as learning_schema
from teacher_app.maintenance import announcement_schema
from teacher_app.maintenance import migrations
from teacher_app.materials import schema as material_schema
from teacher_app.worker import repository as worker_repository
from teacher_app.worker import schema as worker_schema


OWNERS = (
    exam_schema.init_schema,
    material_schema.init_schema,
    assessment_schema.init_schema,
    course_schema.init_schema,
    learning_schema.init_schema,
    announcement_schema.init_schema,
    worker_schema.init_schema,
)


class _SqliteBase:
    def __init__(self, path: Path):
        self.path = path

    def _db_conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"


class _Rows:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def fetchall(self):
        return self._rows


class _RecordingPostgres:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        if "information_schema.columns" in " ".join(sql.split()).lower():
            return _Rows()
        return _Rows()


class PreMigrationSchemaOwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "pre-migration.sqlite"

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn

    def _run_owners(self):
        conn = self._connect()
        try:
            for owner in OWNERS:
                owner(conn, "sqlite")
        finally:
            conn.close()

    def _tables(self):
        conn = self._connect()
        try:
            return {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()

    def _columns(self, table):
        conn = self._connect()
        try:
            return {
                row["name"]: row
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
        finally:
            conn.close()

    def test_fresh_sqlite_owns_exact_pre_migration_base_without_qbank_or_r2_tables(self):
        self._run_owners()
        tables = self._tables()
        self.assertTrue(
            {
                "exam_records",
                "materials",
                "quiz_categories",
                "quiz_publications",
                "quiz_questions",
                "courses",
                "material_progress",
                "announcements",
                "material_jobs",
            }.issubset(tables)
        )
        self.assertNotIn("r2_upload_reservations", tables)
        self.assertNotIn("r2_usage_ledger", tables)
        self.assertNotIn("material_worker_heartbeats", tables)
        self.assertNotIn("material_upload_sessions", tables)

        question_columns = self._columns("quiz_questions")
        self.assertTrue({"answer_config", "difficulty", "active"}.issubset(question_columns))
        for later_column in (
            "domain",
            "topic",
            "subtopic",
            "learning_objective",
            "cognitive_level",
            "tags",
            "source_material_id",
            "review_source",
            "status",
            "origin",
            "version",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
            "normalized_hash",
        ):
            self.assertNotIn(later_column, question_columns)

        self.assertTrue(
            {
                "course_id",
                "review_status",
                "review_comment",
                "quiz_category_id",
                "passing_score",
                "publication_id",
                "publication_hash",
            }.issubset(self._columns("exam_records"))
        )
        self.assertIn("course_id", self._columns("materials"))
        self.assertTrue(
            {
                "learning_objectives",
                "estimated_minutes",
                "start_date",
                "end_date",
                "material_order",
            }.issubset(self._columns("courses"))
        )

    def test_schema_owners_are_idempotent_and_worker_insert_works_before_release_migrations(self):
        self._run_owners()
        self._run_owners()
        conn = self._connect()
        try:
            worker_repository.insert_material_job_on_connection(
                conn,
                "sqlite",
                {
                    "id": "job-1",
                    "created_at": "2026-09-18T00:00:00Z",
                    "updated_at": "2026-09-18T00:00:00Z",
                    "available_at": "2026-09-18T00:00:00Z",
                    "staging_path": "C:/tmp/source.pdf",
                },
            )
            row = conn.execute("SELECT * FROM material_jobs WHERE id='job-1'").fetchone()
        finally:
            conn.close()
        self.assertEqual(row["staging_backend"], "local")
        self.assertEqual(row["worker_last_seen"], "")
        self.assertEqual(row["cleanup_pending"], 0)

    def test_old_shape_tables_are_extended_without_replacing_rows(self):
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE exam_records (
                    id TEXT PRIMARY KEY,created_at TEXT NOT NULL,name TEXT NOT NULL,
                    emp_id TEXT NOT NULL,role TEXT NOT NULL,evaluator_name TEXT,evaluator_title TEXT,
                    quiz_title TEXT NOT NULL,score INTEGER NOT NULL,status TEXT NOT NULL,
                    correct_count INTEGER NOT NULL DEFAULT 0,wrong_count INTEGER NOT NULL DEFAULT 0,
                    answers_detail TEXT NOT NULL
                );
                INSERT INTO exam_records VALUES ('rec-1','old','Old User','E1','learner',NULL,NULL,'Old Quiz',80,'合格',1,0,'[]');
                CREATE TABLE materials (
                    id TEXT PRIMARY KEY,filename TEXT NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',folder TEXT NOT NULL,page_count INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL,storage_filename TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1
                );
                INSERT INTO materials VALUES ('mat-1','a.pdf','Old Material','','','mat-1',1,'old','source.pdf',1);
                CREATE TABLE quiz_categories (
                    id TEXT PRIMARY KEY,group_key TEXT NOT NULL DEFAULT 'grpBio',title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',sort_order INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1
                );
                INSERT INTO quiz_categories VALUES ('quiz-1','grpBio','Old Quiz','',0,'old',1);
                CREATE TABLE quiz_questions (
                    id TEXT PRIMARY KEY,quiz_category_id TEXT NOT NULL,tag TEXT NOT NULL DEFAULT '',
                    question TEXT NOT NULL,question_type TEXT NOT NULL DEFAULT 'choice',image_url TEXT NOT NULL DEFAULT '',
                    options TEXT NOT NULL,correct INTEGER NOT NULL DEFAULT 0,explanation TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0
                );
                INSERT INTO quiz_questions VALUES ('q-1','quiz-1','','Old question','choice','','[]',0,'',0);
                CREATE TABLE courses (
                    id TEXT PRIMARY KEY,training_area TEXT NOT NULL DEFAULT 'pgy',group_key TEXT NOT NULL DEFAULT 'grpBio',
                    title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',sort_order INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1
                );
                INSERT INTO courses VALUES ('course-1','pgy','grpBio','Old Course','',0,'old',1);
                CREATE TABLE material_jobs (
                    id TEXT PRIMARY KEY,status TEXT NOT NULL DEFAULT 'queued',priority INTEGER NOT NULL DEFAULT 50,
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL,available_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',finished_at TEXT NOT NULL DEFAULT '',attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,stage TEXT NOT NULL DEFAULT '等待處理',detail TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL DEFAULT '{}',staging_path TEXT NOT NULL,material_id TEXT NOT NULL DEFAULT '',
                    source_sha256 TEXT NOT NULL DEFAULT '',source_bytes INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL DEFAULT '{}',worker_id TEXT NOT NULL DEFAULT '',cancel_requested INTEGER NOT NULL DEFAULT 0
                );
                INSERT INTO material_jobs (id,created_at,updated_at,available_at,staging_path) VALUES ('old-job','old','old','old','old.pdf');
                """
            )
            exam_schema.init_schema(conn, "sqlite")
            material_schema.init_schema(conn, "sqlite")
            assessment_schema.init_schema(conn, "sqlite")
            course_schema.init_schema(conn, "sqlite")
            worker_schema.init_schema(conn, "sqlite")
            exam = conn.execute("SELECT name,course_id,review_status FROM exam_records WHERE id='rec-1'").fetchone()
            material = conn.execute("SELECT title,storage_backend,course_id FROM materials WHERE id='mat-1'").fetchone()
            category = conn.execute("SELECT title,training_area,draw_count,course_id FROM quiz_categories WHERE id='quiz-1'").fetchone()
            question = conn.execute("SELECT question,answer_config,difficulty,active FROM quiz_questions WHERE id='q-1'").fetchone()
            course = conn.execute("SELECT title,material_order FROM courses WHERE id='course-1'").fetchone()
            job = conn.execute("SELECT id,staging_backend,worker_last_seen,cleanup_pending FROM material_jobs WHERE id='old-job'").fetchone()
        finally:
            conn.close()

        self.assertEqual(tuple(exam), ("Old User", "", "completed"))
        self.assertEqual(tuple(material), ("Old Material", "local", ""))
        self.assertEqual(tuple(category), ("Old Quiz", "internal", 0, ""))
        self.assertEqual(tuple(question), ("Old question", "{}", "standard", 1))
        self.assertEqual(tuple(course), ("Old Course", "[]"))
        self.assertEqual(tuple(job), ("old-job", "local", "", 0))

    def test_release_migrations_layer_cleanly_on_fresh_canonical_base(self):
        self._run_owners()
        applied = migrations.apply_migrations(_SqliteBase(self.path))
        self.assertIn("0068-external-interactive-media", applied)
        self.assertIn("0067-r2-free-budget-guard", applied)
        self.assertEqual(migrations.apply_migrations(_SqliteBase(self.path)), [])
        self.assertIn("domain", self._columns("quiz_questions"))
        self.assertIn("normalized_hash", self._columns("quiz_questions"))
        tables = self._tables()
        self.assertIn("r2_upload_reservations", tables)
        self.assertIn("r2_usage_ledger", tables)

    def test_postgres_ddl_uses_native_jsonb_and_boolean_defaults(self):
        conn = _RecordingPostgres()
        for owner in OWNERS:
            owner(conn, "postgres")
        sql = "\n".join(statement for statement, _params in conn.calls)
        self.assertIn("answers_detail JSONB NOT NULL", sql)
        self.assertIn("draw_rules JSONB NOT NULL DEFAULT '{}'::jsonb", sql)
        self.assertIn("snapshot JSONB NOT NULL", sql)
        self.assertIn("options JSONB NOT NULL", sql)
        self.assertIn("answer_config JSONB NOT NULL DEFAULT '{}'::jsonb", sql)
        self.assertIn("active BOOLEAN NOT NULL DEFAULT TRUE", sql)
        self.assertIn("payload JSONB NOT NULL DEFAULT '{}'::jsonb", sql)
        self.assertIn("source_bytes BIGINT NOT NULL DEFAULT 0", sql)
        self.assertIn("cancel_requested BOOLEAN NOT NULL DEFAULT FALSE", sql)
        self.assertIn("cleanup_pending BOOLEAN NOT NULL DEFAULT FALSE", sql)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS r2_upload_reservations", sql)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS r2_usage_ledger", sql)

        self._run_owners()
        self.assertEqual(
            str(self._columns("material_jobs")["source_bytes"]["type"]).upper(),
            "INTEGER",
        )


if __name__ == "__main__":
    unittest.main()
