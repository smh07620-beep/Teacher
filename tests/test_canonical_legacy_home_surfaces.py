import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

from teacher_app.command_center.dashboard_routes import register_dashboard_routes
from teacher_app.exams.record_routes import register_record_routes
from teacher_app.learning.progress_routes import register_progress_routes
from teacher_app.maintenance.announcement_routes import register_announcement_routes


class _Base:
    def __init__(self, app):
        self.app = app
        self.user = None

    def _current_user(self):
        return self.user


class CanonicalLegacyHomeSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "home-surfaces.db"
        self._create_schema()

        connection_patch = patch(
            "teacher_app.common.db.get_connection",
            side_effect=self._connect,
        )
        connection_patch.start()
        self.addCleanup(connection_patch.stop)

        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.base = _Base(self.app)
        register_announcement_routes(self.base)
        register_progress_routes(self.base)
        register_dashboard_routes(self.base)
        self.client = self.app.test_client()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def _sql(self, sql, params=()):
        conn, _kind = self._connect()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _create_schema(self):
        conn, _kind = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE announcements (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    published_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE material_progress (
                    emp_id TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    material_id TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY (emp_id, material_id)
                );
                CREATE TABLE materials (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    training_area TEXT NOT NULL DEFAULT 'internal',
                    course_id TEXT NOT NULL DEFAULT '',
                    folder TEXT NOT NULL DEFAULT '',
                    page_count INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE courses (
                    id TEXT PRIMARY KEY,
                    training_area TEXT NOT NULL DEFAULT 'pgy',
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    learning_objectives TEXT NOT NULL DEFAULT '',
                    estimated_minutes INTEGER NOT NULL DEFAULT 0,
                    start_date TEXT NOT NULL DEFAULT '',
                    end_date TEXT NOT NULL DEFAULT '',
                    material_order TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE quiz_categories (
                    id TEXT PRIMARY KEY,
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    training_area TEXT NOT NULL DEFAULT 'internal',
                    course_id TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    passing_score INTEGER NOT NULL DEFAULT 80,
                    published_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE exam_records (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    emp_id TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT '',
                    evaluator_name TEXT NOT NULL DEFAULT '',
                    evaluator_title TEXT NOT NULL DEFAULT '',
                    quiz_title TEXT NOT NULL DEFAULT '',
                    score INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT '',
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    answers_detail TEXT NOT NULL DEFAULT '[]',
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    training_area TEXT NOT NULL DEFAULT 'internal',
                    course_id TEXT NOT NULL DEFAULT '',
                    review_status TEXT NOT NULL DEFAULT 'completed',
                    reviewed_at TEXT NOT NULL DEFAULT '',
                    reviewer_name TEXT NOT NULL DEFAULT '',
                    review_comment TEXT NOT NULL DEFAULT '',
                    quiz_category_id TEXT NOT NULL DEFAULT '',
                    passing_score INTEGER NOT NULL DEFAULT 80,
                    publication_id TEXT NOT NULL DEFAULT '',
                    publication_hash TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE pgy_assessments (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    assessment_type TEXT NOT NULL DEFAULT '',
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    name TEXT NOT NULL DEFAULT '',
                    emp_id TEXT NOT NULL DEFAULT '',
                    evaluator_name TEXT NOT NULL DEFAULT '',
                    evaluator_title TEXT NOT NULL DEFAULT '',
                    assessment_date TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    details TEXT NOT NULL DEFAULT '{}',
                    comments TEXT NOT NULL DEFAULT '',
                    overall_score REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'completed'
                );
                """
            )
        finally:
            conn.close()

    def _seed_learning_surface(self):
        self._sql(
            "INSERT INTO courses "
            "(id,training_area,group_key,title,sort_order,date_added,active) "
            "VALUES (?,?,?,?,?,?,1)",
            ("course1", "pgy", "grpBio", "PGY Course", 0, "2026-01-01"),
        )
        self._sql(
            "INSERT INTO materials "
            "(id,filename,title,group_key,training_area,course_id,date_added,active) "
            "VALUES (?,?,?,?,?,?,?,1)",
            ("mat1", "one.pdf", "Material One", "grpBio", "pgy", "course1", "2026-01-01"),
        )
        self._sql(
            "INSERT INTO quiz_categories "
            "(id,group_key,training_area,course_id,title,date_added,active,passing_score,published_at) "
            "VALUES (?,?,?,?,?,?,1,?,?)",
            ("quiz1", "grpBio", "pgy", "course1", "Quiz One", "2026-01-02", 80, "2026-01-02"),
        )

    def test_exact_endpoint_names_are_registered(self):
        expected = {
            "api_announcements_public",
            "api_announcements_admin",
            "api_announcements_create",
            "api_announcements_update",
            "api_announcements_delete",
            "api_dashboard_me",
            "api_material_progress",
            "api_my_progress",
        }
        self.assertTrue(expected.issubset(self.app.view_functions))

    def test_registration_replaces_existing_legacy_handlers_without_duplicate_rules(self):
        app = Flask("legacy-replacement")
        base = _Base(app)

        legacy_announcement = lambda: "legacy-announcement"
        legacy_progress = lambda: "legacy-progress"
        legacy_dashboard = lambda: "legacy-dashboard"

        app.add_url_rule(
            "/api/announcements",
            endpoint="api_announcements_public",
            view_func=legacy_announcement,
            methods=["GET"],
        )
        app.add_url_rule(
            "/api/material-progress",
            endpoint="api_material_progress",
            view_func=legacy_progress,
            methods=["POST"],
        )
        app.add_url_rule(
            "/api/dashboard/me",
            endpoint="api_dashboard_me",
            view_func=legacy_dashboard,
            methods=["GET"],
        )

        before = list(app.url_map.iter_rules())
        register_announcement_routes(base)
        register_progress_routes(base)
        register_dashboard_routes(base)
        after = list(app.url_map.iter_rules())

        self.assertEqual(len(after), len(before) + 5)
        self.assertIsNot(app.view_functions["api_announcements_public"], legacy_announcement)
        self.assertIsNot(app.view_functions["api_material_progress"], legacy_progress)
        self.assertIsNot(app.view_functions["api_dashboard_me"], legacy_dashboard)

    def test_routes_accept_flask_app_and_use_request_bound_canonical_actor(self):
        app = Flask("direct-canonical-routes")
        app.config.update(TESTING=True, SECRET_KEY="test")
        actor = {"user": {"username": "root", "role": "system_admin"}}

        @app.before_request
        def bind_actor():
            g.teacher_user = actor["user"]

        register_announcement_routes(app)
        register_progress_routes(app)
        register_dashboard_routes(app)
        register_record_routes(app)

        self.assertTrue({
            "api_announcements_admin",
            "api_material_progress",
            "api_my_progress",
            "api_dashboard_me",
            "api_review_record",
            "api_create_record",
            "api_list_records",
            "api_clear_records",
        }.issubset(app.view_functions))
        client = app.test_client()
        self.assertEqual(client.get("/api/announcements/admin").status_code, 200)
        self.assertEqual(client.get("/api/records").status_code, 200)

        actor["user"] = None
        self.assertEqual(client.get("/api/records").status_code, 401)
        with patch.dict("os.environ", {"ADMIN_KEY": "test-admin-key"}, clear=False):
            headers = {"X-Admin-Key": "test-admin-key"}
            self.assertEqual(
                client.get("/api/announcements/admin", headers=headers).status_code,
                401,
            )
            self.assertEqual(client.get("/api/records", headers=headers).status_code, 401)

    def test_announcements_preserve_public_admin_and_crud_contracts(self):
        self._sql(
            "INSERT INTO announcements VALUES (?,?,?,?,?,?)",
            ("old", "Old", "body", 1, "2026-01-01", "2026-01-01"),
        )
        self._sql(
            "INSERT INTO announcements VALUES (?,?,?,?,?,?)",
            ("new", "New", "body", 1, "2026-02-01", "2026-02-01"),
        )
        self._sql(
            "INSERT INTO announcements VALUES (?,?,?,?,?,?)",
            ("hidden", "Hidden", "body", 0, "2026-03-01", ""),
        )

        public = self.client.get("/api/announcements?limit=1")
        self.assertEqual(public.status_code, 200)
        self.assertEqual([item["id"] for item in public.get_json()], ["new"])

        denied = self.client.get("/api/announcements/admin")
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(
            denied.get_json(),
            {
                "error": "請先以管理者帳號登入。",
                "loginRequired": True,
            },
        )

        self.base.user = {"username": "student1", "role": "student"}
        forbidden = self.client.get("/api/announcements/admin")
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(
            forbidden.get_json(),
            {"error": "權限不足：此功能限教學管理者使用。"},
        )

        self.base.user = {"username": "root", "role": "system_admin"}
        admin = self.client.get("/api/announcements/admin")
        self.assertEqual([item["id"] for item in admin.get_json()], ["hidden", "new", "old"])

        invalid = self.client.post("/api/announcements", json={"title": "   "})
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.get_json(), {"error": "公告標題不能空白"})

        created = self.client.post(
            "/api/announcements",
            json={"title": "  Created  ", "body": " text ", "active": False},
        )
        self.assertEqual(created.status_code, 201)
        created_body = created.get_json()
        self.assertEqual(created_body["title"], "Created")
        self.assertEqual(created_body["body"], "text")
        self.assertFalse(created_body["active"])
        self.assertEqual(created_body["publishedAt"], "")

        updated = self.client.patch(
            f"/api/announcements/{created_body['id']}",
            json={"active": True},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.get_json()["active"])
        self.assertTrue(updated.get_json()["publishedAt"])

        deleted = self.client.delete(f"/api/announcements/{created_body['id']}")
        self.assertEqual(deleted.get_json(), {"ok": True})
        missing = self.client.delete(f"/api/announcements/{created_body['id']}")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.get_json(), {"error": "找不到公告"})

    def test_progress_routes_preserve_login_completion_and_course_contract(self):
        self._seed_learning_surface()

        denied = self.client.post("/api/material-progress", json={"materialId": "mat1"})
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(
            denied.get_json(),
            {"error": "請先登入後再使用教材。", "loginRequired": True},
        )

        self.base.user = {"username": "student1", "empId": "S001", "name": "Student One"}
        completed = self.client.post("/api/material-progress", json={"materialId": "mat1"})
        self.assertEqual(completed.status_code, 200)
        self.assertTrue(completed.get_json()["ok"])
        self.assertTrue(completed.get_json()["completedAt"])

        self._sql(
            "INSERT INTO exam_records "
            "(id,created_at,name,emp_id,score,status,group_key,training_area,course_id,"
            "review_status,quiz_category_id,passing_score) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "record1",
                "2026-02-01",
                "Student One",
                "S001",
                90,
                "pass",
                "grpBio",
                "pgy",
                "course1",
                "completed",
                "quiz1",
                80,
            ),
        )
        response = self.client.get("/api/my-progress?area=pgy&group=grpBio")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIn("mat1", body["materialsCompleted"])
        self.assertEqual(body["records"][0]["quizCategoryId"], "quiz1")
        self.assertEqual(body["courses"][0]["materialsTotal"], 1)
        self.assertEqual(body["courses"][0]["materialsCompleted"], 1)
        self.assertTrue(body["courses"][0]["examRequired"])
        self.assertTrue(body["courses"][0]["examPassed"])
        self.assertTrue(body["courses"][0]["completed"])

    def test_dashboard_preserves_counts_pending_exam_and_latest_shapes(self):
        self._seed_learning_surface()
        self._sql(
            "INSERT INTO quiz_categories "
            "(id,group_key,training_area,course_id,title,date_added,active,passing_score,published_at) "
            "VALUES (?,?,?,?,?,?,1,?,?)",
            ("quiz2", "grpBio", "pgy", "course1", "Quiz Two", "2026-03-01", 70, "2026-03-01"),
        )
        self._sql(
            "INSERT INTO material_progress VALUES (?,?,?,?)",
            ("S001", "Student One", "mat1", "2026-02-01"),
        )
        self._sql(
            "INSERT INTO exam_records "
            "(id,created_at,name,emp_id,score,status,group_key,training_area,course_id,"
            "review_status,quiz_category_id,passing_score) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("passed", "2026-04-01", "Student One", "S001", 90, "pass", "grpBio", "pgy", "course1", "completed", "quiz1", 80),
        )
        self._sql(
            "INSERT INTO exam_records "
            "(id,created_at,name,emp_id,score,status,group_key,training_area,course_id,"
            "review_status,quiz_category_id,passing_score) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("pending", "2026-05-01", "Student One", "S001", 100, "pass", "grpBio", "pgy", "course1", "pending", "quiz2", 70),
        )
        self._sql(
            "INSERT INTO pgy_assessments "
            "(id,created_at,assessment_type,group_key,name,emp_id,evaluator_name,evaluator_title,"
            "assessment_date,title,details,comments,overall_score,status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("a1", "2026-06-01", "epa", "grpBio", "Student One", "S001", "Teacher", "MD", "2026-06-01", "EPA", "{}", "", 4.5, "completed"),
        )

        denied = self.client.get("/api/dashboard/me")
        self.assertEqual(denied.status_code, 401)
        self.base.user = {"username": "student1", "empId": "S001", "name": "Student One"}
        response = self.client.get("/api/dashboard/me")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["empId"], "S001")
        self.assertEqual(body["materialsTotal"], 1)
        self.assertEqual(body["materialsCompleted"], 1)
        self.assertEqual(body["examsTotal"], 2)
        self.assertEqual(body["examsPassed"], 1)
        self.assertEqual(body["examsPending"], 1)
        self.assertEqual(body["essayReviewsPending"], 1)
        self.assertEqual(body["teacherAssessmentsCompleted"], 1)
        self.assertEqual(body["progressPercent"], 67)
        self.assertEqual([item["id"] for item in body["pendingExams"]], ["quiz2"])
        self.assertEqual(body["latestExam"]["id"], "pending")
        self.assertEqual(body["latestAssessment"]["id"], "a1")


if __name__ == "__main__":
    unittest.main()
