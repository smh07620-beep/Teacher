import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

from teacher_app.assessments import routes, schema


class AssessmentWorkflowIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "assessment.sqlite"

        def connect():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.isolation_level = None
            return conn, "sqlite"

        self.connect = connect
        conn, kind = connect()
        try:
            schema.init_schema(conn, kind)
            conn.execute(
                "CREATE TABLE materials (id TEXT PRIMARY KEY, category TEXT NOT NULL DEFAULT '')"
            )
            conn.execute(
                "INSERT INTO quiz_categories(id,group_key,training_area,title,date_added,active,review_status) "
                "VALUES(?,?,?,?,?,?,?)",
                ("cat-1", "grpBio", "internal", "考卷", "now", 0, "draft"),
            )
            conn.execute(
                "INSERT INTO quiz_questions(id,quiz_category_id,tag,question,question_type,options,correct,answer_config,sort_order,active) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("q-1", "cat-1", "一般", "題目", "choice", '["A","B"]', 0, "{}", 0, 1),
            )
        finally:
            conn.close()

        self.db_patch = patch("teacher_app.common.db.get_connection", side_effect=connect)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.actor = {
            "username": "root",
            "name": "Server Admin",
            "role": "system_admin",
            "professionalTitle": "教學行政管理師",
            "preferredGroup": "grpBio",
        }

        @self.app.before_request
        def bind_actor():
            g.teacher_user = self.actor

        routes.register_assessment_routes(self.app)
        self.client = self.app.test_client()

    def category(self):
        conn, _ = self.connect()
        try:
            return dict(conn.execute("SELECT * FROM quiz_categories WHERE id='cat-1'").fetchone())
        finally:
            conn.close()

    def test_settings_patch_cannot_self_approve_or_publish(self):
        response = self.client.patch(
            "/api/quiz-categories/cat-1",
            json={
                "active": True,
                "reviewStatus": "approved",
                "reviewerName": "Browser Supplied",
                "reviewedAt": "fake",
                "publishedAt": "fake",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        item = self.category()
        self.assertEqual(item["review_status"], "draft")
        self.assertEqual(item["reviewer_name"], "")
        self.assertEqual(item["reviewed_at"], "")
        self.assertEqual(item["published_at"], "")
        self.assertEqual(item["active"], 0)

    def test_review_and_publish_identity_comes_from_request_actor(self):
        reviewed = self.client.post(
            "/api/quiz-categories/cat-1/review",
            json={"reviewerName": "Browser Supplied"},
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.get_data(as_text=True))
        self.assertEqual(reviewed.get_json()["reviewerName"], "Server Admin")
        self.assertEqual(reviewed.get_json()["reviewerTitle"], "教學行政管理師")
        self.assertEqual(self.category()["reviewer_name"], "Server Admin")
        self.assertEqual(self.category()["reviewer_title"], "教學行政管理師")

        published = self.client.post("/api/quiz-categories/cat-1/publish")
        self.assertEqual(published.status_code, 200, published.get_data(as_text=True))
        self.assertEqual(published.get_json()["publishedBy"], "Server Admin")

        conn, _ = self.connect()
        try:
            row = conn.execute(
                "SELECT snapshot FROM quiz_publications WHERE quiz_category_id='cat-1'"
            ).fetchone()
        finally:
            conn.close()
        snapshot = json.loads(row["snapshot"])
        self.assertEqual(snapshot["schemaVersion"], 2)
        self.assertEqual(snapshot["category"]["publishedBy"], "Server Admin")
        self.assertEqual(snapshot["category"]["reviewerTitle"], "教學行政管理師")
        self.assertEqual(snapshot["questions"][0]["version"], 1)
        self.assertRegex(snapshot["questions"][0]["questionHash"], r"^[0-9a-f]{64}$")

    def test_category_delete_resolves_scope_from_target_category(self):
        self.actor = {
            "username": "teacher",
            "name": "Bio Teacher",
            "role": "clinical_teacher",
            "preferredGroup": "grpMicro",
        }
        denied = self.client.delete("/api/quiz-categories/cat-1")
        self.assertEqual(denied.status_code, 403, denied.get_data(as_text=True))
        self.assertEqual(denied.get_json(), {"error": "此資源不在你的授權範圍。"})
        self.assertEqual(self.category()["group_key"], "grpBio")

        self.actor = {**self.actor, "preferredGroup": "grpBio"}
        own = self.client.delete("/api/quiz-categories/cat-1")
        self.assertEqual(own.status_code, 200, own.get_data(as_text=True))
        conn, _ = self.connect()
        try:
            self.assertIsNone(conn.execute("SELECT id FROM quiz_categories WHERE id='cat-1'").fetchone())
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
