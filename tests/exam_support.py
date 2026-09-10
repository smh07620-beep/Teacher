import os
import sqlite3
import tempfile
from pathlib import Path

from flask import Flask


class ExamBase:
    def __init__(self):
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.path = Path(path)
        self.app = Flask(__name__)
        self.user = {"username": "student1", "name": "學員一", "empId": "S001", "role": "student"}
        self.category = {
            "id": "quiz1", "title": "血液學測驗", "active": True, "group": "grpBio", "area": "internal",
            "courseId": "course1", "passingScore": 60, "publicationId": "pub1", "publicationHash": "hash1",
        }
        self.questions = [
            {"id": "q1", "question": "2+2?", "questionType": "choice", "options": ["3", "4"],
             "correct": 1, "explanation": "four", "answerConfig": {}, "tag": "基礎", "active": True},
            {"id": "q2", "question": "說明原因", "questionType": "essay", "correct": "secret",
             "answerConfig": {"acceptedAnswers": ["secret"]}, "tag": "申論", "active": True},
        ]
        conn, _ = self._db_conn()
        try:
            conn.execute("""CREATE TABLE exam_records (
                id TEXT PRIMARY KEY, created_at TEXT, name TEXT, emp_id TEXT, role TEXT, evaluator_name TEXT,
                evaluator_title TEXT, quiz_title TEXT, score INTEGER, status TEXT, correct_count INTEGER,
                wrong_count INTEGER, answers_detail TEXT, group_key TEXT, training_area TEXT, course_id TEXT,
                review_status TEXT, quiz_category_id TEXT, passing_score INTEGER, publication_id TEXT,
                publication_hash TEXT)""")
        finally:
            conn.close()

    def close(self):
        self.path.unlink(missing_ok=True)

    def _db_conn(self):
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def _current_user(self):
        return self.user

    @staticmethod
    def normalize_role(value):
        return str(value or "student")

    def get_quiz_category(self, category_id):
        return dict(self.category) if category_id == self.category["id"] else None

    def list_quiz_questions(self, category_id):
        return [dict(question) for question in self.questions] if category_id == self.category["id"] else []


def submit_payload(answers=None):
    return {"answers": [1, "essay response"] if answers is None else answers,
            "evaluatorName": "教師", "evaluatorTitle": "醫師", "examineeRole": "student"}
