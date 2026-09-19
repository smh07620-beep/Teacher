"""Behavior coverage for the user-facing 6.8.1 exposure workflows."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

from external_media_68 import register_external_media
from question_bank_68 import register_question_bank


class _Base:
    DEFAULT_GROUP = "grpBio"
    DEFAULT_TRAINING_AREA = "internal"

    def __init__(self):
        handle, name = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        Path(name).unlink(missing_ok=True)
        self.path = Path(name)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, DIRECT_MEDIA_ALLOWLIST=[])
        conn, _ = self._db_conn()
        try:
            conn.executescript("""
            CREATE TABLE quiz_questions (id TEXT PRIMARY KEY, quiz_category_id TEXT, tag TEXT, question TEXT,
              question_type TEXT, options TEXT, correct INTEGER, explanation TEXT, domain TEXT DEFAULT '',
              topic TEXT DEFAULT '', subtopic TEXT DEFAULT '', learning_objective TEXT DEFAULT '', difficulty TEXT,
              cognitive_level TEXT, tags TEXT, source_material_id TEXT, review_source TEXT, status TEXT, origin TEXT,
              updated_at TEXT, normalized_hash TEXT, active INTEGER DEFAULT 1, version INTEGER DEFAULT 1,
              reviewed_by TEXT DEFAULT '', reviewed_at TEXT DEFAULT '', sort_order INTEGER DEFAULT 0);
            CREATE TABLE exam_blueprints (id TEXT PRIMARY KEY, quiz_category_id TEXT, question_count INTEGER,
              quotas TEXT, exclude_recent INTEGER, created_by TEXT, created_at TEXT);
            CREATE TABLE exam_blueprint_snapshots (id TEXT PRIMARY KEY, blueprint_id TEXT UNIQUE,
              quiz_category_id TEXT, questions TEXT, created_at TEXT);
            CREATE TABLE question_attempt_analytics (question_id TEXT, attempt_id TEXT, selected_option TEXT,
              is_correct INTEGER, created_at TEXT, PRIMARY KEY(question_id, attempt_id));
            CREATE TABLE materials (id TEXT PRIMARY KEY, filename TEXT, title TEXT, description TEXT, category TEXT,
              group_key TEXT, training_area TEXT, folder TEXT, page_count INTEGER, date_added TEXT,
              storage_filename TEXT, storage_backend TEXT, storage_key TEXT, slides_prefix TEXT, storage_meta TEXT,
              material_type TEXT, atlas_meta TEXT, active INTEGER, course_id TEXT);
            CREATE TABLE external_media (id TEXT PRIMARY KEY, material_id TEXT UNIQUE, provider TEXT,
              canonical_url TEXT, video_id TEXT, created_at TEXT, updated_at TEXT);
            """)
        finally:
            conn.close()

    def close(self):
        self.path.unlink(missing_ok=True)

    def _db_conn(self):
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def require_admin(self):
        return None

    def _current_user(self):
        return {"username": "admin", "role": "system_admin"}

    @staticmethod
    def normalize_group(value):
        return value if value == "grpBio" else "grpBio"

    @staticmethod
    def normalize_area(value):
        return value if value in {"internal", "pgy"} else "internal"

    def get_course(self, _course_id):
        return None

    def get_quiz_category(self, _category_id):
        return None

    def get_material(self, material_id):
        conn, _ = self._db_conn()
        try:
            row = conn.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


class FeatureExposureWorkflow681Tests(unittest.TestCase):
    def setUp(self):
        self.base = _Base()
        self.canonical_db = patch(
            "teacher_app.common.db.get_connection",
            side_effect=self.base._db_conn,
        )
        self.canonical_db.start()
        @self.base.app.before_request
        def bind_teacher_user():
            g.teacher_user = self.base._current_user()
        register_question_bank(self.base)
        register_external_media(self.base)
        self.client = self.base.app.test_client()

    def tearDown(self):
        self.canonical_db.stop()
        self.base.close()

    def draft(self, question="題目一"):
        return self.client.post("/api/question-bank/drafts", json={
            "quizCategoryId": "exam-a", "question": question, "options": ["A", "B"], "correct": 1,
            "explanation": "解析", "topic": "核心", "subtopic": "子題", "learningObjective": "會判讀",
            "difficulty": "medium", "cognitiveLevel": "apply", "tags": ["QC"],
            "sourceMaterialId": "material-a", "reviewSource": {"type": "page", "page": 3, "pageEnd": 4},
            "origin": "ai_generated",
        })

    def test_draft_review_publish_metadata_roundtrip(self):
        created = self.draft()
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        qid = created.get_json()["id"]
        review = self.client.post(f"/api/question-bank/{qid}/review", json={"decision": "accept"})
        self.assertEqual(review.status_code, 200)
        edited = self.client.patch(f"/api/question-bank/{qid}", json={
            "question": "題目一更新", "options": ["A", "B"], "correct": 1, "explanation": "更新解析",
            "topic": "核心", "subtopic": "子題", "learningObjective": "會判讀", "difficulty": "hard",
            "cognitiveLevel": "analyze", "tags": ["QC", "複核"], "sourceMaterialId": "material-b",
            "reviewSource": {"type": "time", "timeStart": 12, "timeEnd": 28}, "status": "published",
            "origin": "ai_generated",
        })
        self.assertEqual(edited.status_code, 200, edited.get_data(as_text=True))
        item = edited.get_json()["item"]
        self.assertEqual(item["learningObjective"], "會判讀")
        self.assertEqual(item["cognitiveLevel"], "analyze")
        self.assertEqual(item["sourceMaterialId"], "material-b")
        self.assertEqual(item["reviewSource"]["timeEnd"], 28)
        self.assertEqual(item["status"], "published")

    def test_blueprint_payload_publish_and_analytics_contract(self):
        ids = []
        for index in range(2):
            response = self.draft(f"題目 {index}")
            ids.append(response.get_json()["id"])
            self.client.post(f"/api/question-bank/{ids[-1]}/review", json={"decision": "accept"})
        blueprint = self.client.post("/api/exam-blueprints", json={
            "quizCategoryId": "exam-a", "questionCount": 2,
            "quotas": {"topic": {"核心": 2}, "difficulty": {"medium": 2}, "cognitive_level": {"apply": 2}},
            "excludeRecent": 0,
        })
        self.assertEqual(blueprint.status_code, 201)
        snapshot = self.client.post(f"/api/exam-blueprints/{blueprint.get_json()['id']}/publish")
        self.assertEqual(snapshot.status_code, 201, snapshot.get_data(as_text=True))
        self.assertTrue(snapshot.get_json()["immutable"])
        analytics = self.client.get(f"/api/questions/{ids[0]}/analytics")
        self.assertEqual(analytics.status_code, 200)
        self.assertFalse(analytics.get_json()["sufficientData"])

    def test_external_material_is_created_without_object_storage_or_worker(self):
        response = self.client.post("/api/materials/external", json={
            "title": "安全影音", "description": "示範", "area": "internal", "group": "grpBio",
            "url": "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        })
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        data = response.get_json()
        self.assertEqual(data["externalMedia"]["provider"], "youtube")
        self.assertEqual(data["material"]["storageBackend"], "external")
        conn, _ = self.base._db_conn()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM external_media").fetchone()[0], 1)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
