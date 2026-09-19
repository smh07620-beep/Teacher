import sqlite3
import unittest

from teacher_app.maintenance import migrations


class QuestionVersionMigrationTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.isolation_level = None
        self.addCleanup(self.conn.close)
        self.conn.executescript(
            """
            CREATE TABLE quiz_categories (
                id TEXT PRIMARY KEY,
                group_key TEXT NOT NULL DEFAULT 'grpBio'
            );
            CREATE TABLE quiz_questions (
                id TEXT PRIMARY KEY,
                quiz_category_id TEXT NOT NULL,
                question TEXT NOT NULL,
                question_type TEXT NOT NULL DEFAULT 'choice',
                options TEXT NOT NULL DEFAULT '[]',
                correct INTEGER NOT NULL DEFAULT 0,
                answer_config TEXT NOT NULL DEFAULT '{}',
                explanation TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                difficulty TEXT NOT NULL DEFAULT 'standard',
                version INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE question_attempt_analytics (
                question_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                selected_option TEXT NOT NULL DEFAULT '',
                is_correct INTEGER NOT NULL DEFAULT 0,
                attempt_score REAL NOT NULL DEFAULT 0,
                response_seconds REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                PRIMARY KEY(question_id,attempt_id)
            );
            INSERT INTO quiz_categories(id,group_key) VALUES('cat-1','grpBio');
            INSERT INTO quiz_questions(
                id,quiz_category_id,question,options,correct,version,updated_at
            ) VALUES('q-1','cat-1','目前內容','["A","B"]',1,4,'2026-09-19T00:00:00+00:00');
            """
        )

    def test_0081_backfills_only_honest_current_baseline(self):
        migrations._question_version_history_81(self.conn, "sqlite")
        rows = self.conn.execute(
            "SELECT question_id,version,question_hash,group_key,change_reason,snapshot "
            "FROM question_versions ORDER BY version"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["question_id"], "q-1")
        self.assertEqual(rows[0]["version"], 4)
        self.assertRegex(rows[0]["question_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(rows[0]["group_key"], "grpBio")
        self.assertEqual(rows[0]["change_reason"], "baseline")

        migrations._question_version_history_81(self.conn, "sqlite")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM question_versions").fetchone()[0],
            1,
        )

    def test_0082_adds_version_identity_without_fabricating_hash(self):
        self.conn.execute(
            "INSERT INTO question_attempt_analytics"
            "(question_id,attempt_id,selected_option,is_correct,created_at) "
            "VALUES('q-1','attempt-old','1',1,'2026-09-19T00:00:00+00:00')"
        )
        migrations._version_aware_item_analytics_82(self.conn, "sqlite")
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(question_attempt_analytics)").fetchall()
        }
        self.assertTrue({"question_version", "question_hash"}.issubset(columns))
        old = self.conn.execute(
            "SELECT question_version,question_hash FROM question_attempt_analytics "
            "WHERE attempt_id='attempt-old'"
        ).fetchone()
        self.assertEqual(old["question_version"], 1)
        self.assertEqual(old["question_hash"], "")


if __name__ == "__main__":
    unittest.main()
