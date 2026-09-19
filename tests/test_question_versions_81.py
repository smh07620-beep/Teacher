import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.assessments import repository


class QuestionVersionHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = str(Path(self.tmp.name) / "question-versions.sqlite")
        self._create_schema()
        self.connection_patch = patch(
            "teacher_app.common.db.get_connection",
            side_effect=self.connect,
        )
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def _create_schema(self):
        conn, _ = self.connect()
        try:
            conn.executescript(
                """
                CREATE TABLE quiz_categories (
                    id TEXT PRIMARY KEY,
                    group_key TEXT NOT NULL,
                    training_area TEXT NOT NULL DEFAULT 'internal'
                );
                CREATE TABLE quiz_questions (
                    id TEXT PRIMARY KEY,
                    quiz_category_id TEXT NOT NULL,
                    tag TEXT NOT NULL DEFAULT '',
                    question TEXT NOT NULL,
                    question_type TEXT NOT NULL DEFAULT 'choice',
                    image_url TEXT NOT NULL DEFAULT '',
                    options TEXT NOT NULL DEFAULT '[]',
                    correct INTEGER NOT NULL DEFAULT 0,
                    answer_config TEXT NOT NULL DEFAULT '{}',
                    explanation TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    difficulty TEXT NOT NULL DEFAULT 'standard',
                    domain TEXT NOT NULL DEFAULT '',
                    topic TEXT NOT NULL DEFAULT '',
                    subtopic TEXT NOT NULL DEFAULT '',
                    learning_objective TEXT NOT NULL DEFAULT '',
                    cognitive_level TEXT NOT NULL DEFAULT 'understand',
                    tags TEXT NOT NULL DEFAULT '[]',
                    source_material_id TEXT NOT NULL DEFAULT '',
                    review_source TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'draft',
                    origin TEXT NOT NULL DEFAULT 'manual',
                    version INTEGER NOT NULL DEFAULT 1,
                    reviewed_by TEXT NOT NULL DEFAULT '',
                    reviewed_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    normalized_hash TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE question_versions (
                    question_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    question_hash TEXT NOT NULL,
                    quiz_category_id TEXT NOT NULL DEFAULT '',
                    group_key TEXT NOT NULL DEFAULT '',
                    snapshot TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL DEFAULT '',
                    change_reason TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(question_id, version)
                );
                INSERT INTO quiz_categories(id,group_key) VALUES('cat-1','grpBio');
                INSERT INTO quiz_questions(
                    id,quiz_category_id,tag,question,question_type,options,correct,
                    explanation,difficulty,topic,cognitive_level,updated_at
                ) VALUES(
                    'q-1','cat-1','一般','原始題目','choice','["A","B"]',1,
                    '說明','standard','topic-a','understand','2026-09-19T00:00:00+00:00'
                );
                """
            )
        finally:
            conn.close()

    def _live(self):
        conn, _ = self.connect()
        try:
            row = conn.execute("SELECT * FROM quiz_questions WHERE id='q-1'").fetchone()
            return dict(row)
        finally:
            conn.close()

    def _update_values(self, **changes):
        live = self._live()
        values = {
            "question": live["question"],
            "options": live["options"],
            "correct": live["correct"],
            "explanation": live["explanation"],
            "topic": live["topic"],
            "subtopic": live["subtopic"],
            "learning_objective": live["learning_objective"],
            "difficulty": live["difficulty"],
            "cognitive_level": live["cognitive_level"],
            "tags": live["tags"],
            "source_material_id": live["source_material_id"],
            "review_source": live["review_source"],
            "status": "draft",
            "origin": live["origin"],
            "updated_at": "2026-09-19T01:00:00+00:00",
            "reviewed_by": "",
            "reviewed_at": "",
        }
        values.update(changes)
        return values

    def test_baseline_content_edit_review_and_delete_preserve_history(self):
        conn, kind = self.connect()
        try:
            inserted = repository.backfill_question_versions_on_connection(
                conn,
                kind,
                created_at="2026-09-19T00:00:00+00:00",
            )
        finally:
            conn.close()
        self.assertEqual(inserted, 1)
        baseline = repository.list_question_versions("q-1")
        self.assertEqual([item["version"] for item in baseline], [1])
        self.assertEqual(baseline[0]["group_key"], "grpBio")

        updated = repository.update_bank_question(
            "q-1",
            self._update_values(question="修改後題目"),
        )
        self.assertEqual(updated["version"], 2)
        versions = repository.list_question_versions("q-1")
        self.assertEqual([item["version"] for item in versions], [2, 1])
        self.assertNotEqual(versions[0]["question_hash"], versions[1]["question_hash"])

        repository.review_bank_question(
            "q-1",
            decision="accept",
            username="teacher",
            stamp="2026-09-19T02:00:00+00:00",
        )
        self.assertEqual(self._live()["version"], 2)
        self.assertEqual(len(repository.list_question_versions("q-1")), 2)

        repository.delete_bank_question("q-1")
        self.assertIsNone(repository.get_bank_question("q-1"))
        self.assertEqual(
            [item["version"] for item in repository.list_question_versions("q-1")],
            [2, 1],
        )

    def test_noop_content_update_does_not_create_version(self):
        conn, kind = self.connect()
        try:
            repository.backfill_question_versions_on_connection(conn, kind)
        finally:
            conn.close()
        updated = repository.update_bank_question("q-1", self._update_values())
        self.assertEqual(updated["version"], 1)
        self.assertEqual(len(repository.list_question_versions("q-1")), 1)


if __name__ == "__main__":
    unittest.main()
