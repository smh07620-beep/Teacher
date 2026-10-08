import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

from teacher_app.assessments import ai_jobs, routes, schema
from teacher_app.materials import repository as material_repository


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
                """CREATE TABLE materials (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
                    group_key TEXT NOT NULL DEFAULT '', training_area TEXT NOT NULL DEFAULT 'internal',
                    course_id TEXT NOT NULL DEFAULT '', folder TEXT NOT NULL DEFAULT '', page_count INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL DEFAULT '', storage_filename TEXT NOT NULL DEFAULT '',
                    storage_backend TEXT NOT NULL DEFAULT 'local', storage_key TEXT NOT NULL DEFAULT '',
                    slides_prefix TEXT NOT NULL DEFAULT '', storage_meta TEXT NOT NULL DEFAULT '{}',
                    material_type TEXT NOT NULL DEFAULT 'standard', atlas_meta TEXT NOT NULL DEFAULT '{}',
                    active INTEGER NOT NULL DEFAULT 1,
                    current_version INTEGER NOT NULL DEFAULT 1,
                    required_completion_version INTEGER NOT NULL DEFAULT 1,
                    version_updated_at TEXT NOT NULL DEFAULT '',
                    version_updated_by TEXT NOT NULL DEFAULT ''
                )"""
            )
            conn.execute("""CREATE TABLE material_versions (
                material_id TEXT NOT NULL, version INTEGER NOT NULL,
                requires_retraining INTEGER NOT NULL DEFAULT 0,
                change_reason TEXT NOT NULL DEFAULT '', published_at TEXT NOT NULL,
                published_by TEXT NOT NULL DEFAULT '', snapshot TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(material_id,version)
            )""")
            conn.execute(
                "INSERT INTO quiz_categories(id,group_key,training_area,title,date_added,active,review_status) "
                "VALUES(?,?,?,?,?,?,?)",
                ("cat-1", "grpBio", "internal", "考卷", "now", 0, "draft"),
            )
            conn.execute(
                "UPDATE quiz_categories SET audience=? WHERE id=?",
                ("一般人員", "cat-1"),
            )
            conn.execute("""CREATE TABLE exam_windows (
                quiz_category_id TEXT PRIMARY KEY, opens_at TEXT NOT NULL DEFAULT '',
                closes_at TEXT NOT NULL DEFAULT '', reminder_enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT '', updated_by TEXT NOT NULL DEFAULT ''
            )""")
            conn.execute(
                "INSERT INTO exam_windows(quiz_category_id,opens_at,closes_at) VALUES(?,?,?)",
                ("cat-1", "2026-01-01T00:00:00+00:00", "2099-12-31T23:59:00+00:00"),
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

    def test_single_exam_response_includes_active_question_count(self):
        # 清單 API 有題數；打開單一考卷時也要有，否則畫面顯示「題庫 0 題」。
        response = self.client.get("/api/quiz-categories/cat-1")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["questionCount"], 1)

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
        self.assertEqual(snapshot["category"]["examWindow"]["opensAt"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(snapshot["category"]["examWindow"]["closesAt"], "2099-12-31T23:59:00+00:00")
        self.assertEqual(snapshot["questions"][0]["version"], 1)
        self.assertRegex(snapshot["questions"][0]["questionHash"], r"^[0-9a-f]{64}$")

    def test_new_material_link_is_persisted_and_ai_job_can_read_same_material(self):
        material_repository.insert_material({
            "id": "mat-new", "filename": "new.pdf", "title": "新教材", "description": "",
            "category": "", "group_key": "grpBio", "training_area": "internal", "course_id": "",
            "folder": "mat-new", "page_count": 1, "date_added": "now",
            "storage_filename": "new.pdf", "storage_backend": "local", "storage_key": "",
            "slides_prefix": "", "storage_meta": "{}", "material_type": "standard",
            "atlas_meta": "{}", "active": True,
        })
        linked = self.client.put(
            "/api/quiz-categories/cat-1/materials",
            json={"materialIds": ["mat-new"]},
        )
        self.assertEqual(linked.status_code, 200, linked.get_data(as_text=True))
        self.assertEqual(linked.get_json()["linkedIds"], ["mat-new"])
        listed = self.client.get("/api/quiz-categories/cat-1/materials")
        self.assertEqual(listed.status_code, 200, listed.get_data(as_text=True))
        item = next(x for x in listed.get_json()["items"] if x["id"] == "mat-new")
        self.assertTrue(item["linked"])

        runtime = type("Runtime", (), {"max_materials": 4, "max_questions": 15})()
        values = ai_jobs.prepare_request(
            {"quizCategoryId": "cat-1", "materialIds": ["mat-new"]},
            runtime,
            self.actor,
        )
        self.assertEqual(values["request"]["materialIds"], ["mat-new"])

    def test_linked_material_version_replacement_keeps_canonical_ai_source(self):
        material_repository.insert_material({
            "id": "mat-versioned", "filename": "v1.pdf", "title": "版本教材", "description": "",
            "category": "", "group_key": "grpBio", "training_area": "internal", "course_id": "",
            "folder": "mat-versioned", "page_count": 1, "date_added": "now",
            "storage_filename": "v1.pdf", "storage_backend": "local", "storage_key": "v1",
            "slides_prefix": "", "storage_meta": "{}", "material_type": "standard",
            "atlas_meta": "{}", "active": True,
        })
        linked = self.client.put("/api/quiz-categories/cat-1/materials", json={"materialIds": ["mat-versioned"]})
        self.assertEqual(linked.status_code, 200, linked.get_data(as_text=True))
        updated = material_repository.replace_material_content_and_publish(
            "mat-versioned",
            content={"filename": "v2.pdf", "title": "版本教材", "storage_filename": "v2.pdf", "storage_backend": "r2", "storage_key": "v2"},
            published_by="root",
            change_reason="更新教材內容",
            requires_retraining=False,
        )
        self.assertEqual(updated["id"], "mat-versioned")
        self.assertEqual(updated["category"], "cat-1")
        runtime = type("Runtime", (), {"max_materials": 4, "max_questions": 15})()
        values = ai_jobs.prepare_request({"quizCategoryId": "cat-1", "materialIds": ["mat-versioned"]}, runtime, self.actor)
        self.assertEqual(values["request"]["materialIds"], ["mat-versioned"])
        self.assertEqual(material_repository.get_material("mat-versioned")["filename"], "v2.pdf")

    def test_publish_fails_closed_when_exam_window_is_missing(self):
        reviewed = self.client.post("/api/quiz-categories/cat-1/review")
        self.assertEqual(reviewed.status_code, 200, reviewed.get_data(as_text=True))
        conn, _ = self.connect()
        try:
            conn.execute("DELETE FROM exam_windows WHERE quiz_category_id='cat-1'")
        finally:
            conn.close()
        published = self.client.post("/api/quiz-categories/cat-1/publish")
        self.assertEqual(published.status_code, 409, published.get_data(as_text=True))
        self.assertEqual(published.get_json()["error"], "發布前必須設定開始時間與最後考核日期")
        self.assertEqual(self.category()["active"], 0)

    def test_publish_fails_closed_when_audience_is_missing(self):
        reviewed = self.client.post("/api/quiz-categories/cat-1/review")
        self.assertEqual(reviewed.status_code, 200, reviewed.get_data(as_text=True))
        conn, _ = self.connect()
        try:
            conn.execute("UPDATE quiz_categories SET audience='' WHERE id='cat-1'")
        finally:
            conn.close()
        published = self.client.post("/api/quiz-categories/cat-1/publish")
        self.assertEqual(published.status_code, 409, published.get_data(as_text=True))
        self.assertEqual(published.get_json()["error"], "發布前必須設定適用人員")
        self.assertEqual(self.category()["active"], 0)

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
