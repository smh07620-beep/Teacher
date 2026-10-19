"""Learner 錯題本 keeps a question until the latest answer is right (2026-10-17)."""
import json
import sqlite3
import unittest
from unittest import mock

from teacher_app.exams import wrong_book


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE exam_attempts (id TEXT, username TEXT, status TEXT, quiz_category_id TEXT, quiz_title TEXT, questions_json TEXT, submitted_at TEXT)")
    conn.execute("CREATE TABLE question_attempt_analytics (question_id TEXT, attempt_id TEXT, selected_option TEXT, is_correct INTEGER, created_at TEXT)")
    return conn


class _NoClose:
    def __init__(self, conn): self.conn = conn
    def execute(self, *a): return self.conn.execute(*a)
    def close(self): pass


class WrongBookTests(unittest.TestCase):
    def test_latest_result_wins_and_answers_stay_private(self):
        conn = _db()
        q1 = {"id": "q1", "question": "鉀離子假性升高原因？", "options": ["溶血", "脫水"], "correct": 0, "explanation": "秘密",
              "answerConfig": {"reviewSource": {"materialId": "m1", "page": 4}}}
        q2 = {"id": "q2", "question": "第二題", "options": ["A", "B"], "correct": 1}
        for aid, when in (("a1", "2026-10-01"), ("a2", "2026-10-10")):
            conn.execute("INSERT INTO exam_attempts VALUES (?,?,?,?,?,?,?)", (aid, "stu", "submitted", "cat", "生化考卷", json.dumps([q1, q2]), when))
        rows = [("q1", "a1", "1", 0), ("q2", "a1", "0", 0), ("q1", "a2", "1", 0), ("q2", "a2", "1", 1)]
        conn.executemany("INSERT INTO question_attempt_analytics VALUES (?,?,?,?, '')", rows)
        with mock.patch.object(wrong_book.repo, "_connect", return_value=(_NoClose(conn), "sqlite")):
            book = wrong_book.build({"username": "STU"})
        self.assertEqual([i["questionId"] for i in book["items"]], ["q1"])  # q2 was fixed in the newer attempt
        item = book["items"][0]
        self.assertEqual(item["yourAnswer"], "B")
        self.assertEqual(item["reviewSource"]["page"], 4)
        self.assertNotIn("correct", json.dumps(item))
        self.assertNotIn("秘密", json.dumps(item, ensure_ascii=False))

    def test_anonymous_gets_nothing(self):
        self.assertEqual(wrong_book.build({})["count"], 0)


if __name__ == "__main__":
    unittest.main()
