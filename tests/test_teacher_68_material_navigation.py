"""Regression coverage for the 6.8/6.8.1 material-navigation and RBAC fixes."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as legacy_app
import pgy_app


ROOT = Path(__file__).parents[1]


class MaterialReadAccess68Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "teacher-navigation.sqlite"
        self.db_patch = patch.object(legacy_app, "_db_conn", self.connect)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        legacy_app.init_user_accounts_db()
        legacy_app.init_materials_db()
        legacy_app.init_quiz_db()
        legacy_app.init_learning_db()
        conn, _ = self.connect()
        try:
            conn.execute(
                "CREATE TABLE admin_elevations ("
                "username TEXT PRIMARY KEY, elevated_at TEXT NOT NULL, "
                "expires_at TEXT NOT NULL, session_version INTEGER NOT NULL DEFAULT 0)"
            )
            users = (
                ("education-admin", "Education Admin", "E001", "education_admin", "grpHema"),
                ("group-leader", "Group Leader", "G001", "group_leader", "grpHema"),
                ("clinical-teacher", "Clinical Teacher", "T001", "clinical_teacher", "grpHema"),
                ("student-user", "Student", "S001", "student", "grpHema"),
                ("auditor-user", "Auditor", "A001", "auditor", "grpHema"),
            )
            for username, display_name, emp_id, role, group in users:
                conn.execute(
                    "INSERT INTO user_accounts "
                    "(username,password_hash,display_name,emp_id,role,preferred_area,preferred_group,active,session_version,created_at,updated_at,last_login_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        username, generate_password_hash("test-password"), display_name,
                        emp_id, role, "internal", group, 1, 1,
                        "2026-01-01", "2026-01-01", "",
                    ),
                )
        finally:
            conn.close()
        self.client = pgy_app.app.test_client()

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def login(self, username="education-admin"):
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": "test-password"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def test_education_admin_session_can_read_slides(self):
        self.login()
        response = self.client.get("/api/slides?area=internal")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def test_anonymous_slides_request_is_401(self):
        response = self.client.get("/api/slides?area=internal")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.get_json()["loginRequired"])

    def test_education_admin_can_use_cross_group_material_management_without_elevation(self):
        self.login("education-admin")
        listing = self.client.get("/api/slides/admin")
        self.assertEqual(listing.status_code, 200, listing.get_data(as_text=True))
        upload = self.client.post(
            "/api/slides/upload",
            data={"group": "grpBio", "area": "internal"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(upload.status_code, 400, upload.get_data(as_text=True))
        self.assertIn("未收到檔案", upload.get_data(as_text=True))
        self.assertFalse(upload.get_json().get("elevationRequired", False))

    def test_group_leader_can_upload_only_to_own_group(self):
        self.login("group-leader")
        own = self.client.post(
            "/api/slides/upload",
            data={"group": "grpHema", "area": "internal"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(own.status_code, 400, own.get_data(as_text=True))
        self.assertIn("未收到檔案", own.get_data(as_text=True))

        other = self.client.post(
            "/api/slides/upload",
            data={"group": "grpBio", "area": "internal"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(other.status_code, 403, other.get_data(as_text=True))
        self.assertIn("授權範圍", other.get_data(as_text=True))

    def test_clinical_teacher_can_upload_only_to_own_group(self):
        self.login("clinical-teacher")
        own = self.client.post(
            "/api/slides/upload",
            data={"group": "grpHema", "area": "internal"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(own.status_code, 400, own.get_data(as_text=True))
        other = self.client.post(
            "/api/slides/upload",
            data={"group": "grpBio", "area": "internal"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(other.status_code, 403, other.get_data(as_text=True))

    def test_group_leader_question_management_is_group_scoped(self):
        self.login("group-leader")
        own = self.client.post(
            "/api/quiz-categories",
            json={"group": "grpHema", "area": "internal", "title": "Own group quiz"},
            headers={"Origin": "http://localhost"},
        )
        self.assertNotEqual(own.status_code, 403, own.get_data(as_text=True))

        other = self.client.post(
            "/api/quiz-categories",
            json={"group": "grpBio", "area": "internal", "title": "Other group quiz"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(other.status_code, 403, other.get_data(as_text=True))

    def test_student_and_auditor_cannot_mutate_materials(self):
        for username in ("student-user", "auditor-user"):
            self.login(username)
            response = self.client.post(
                "/api/slides/upload",
                data={"group": "grpHema", "area": "internal"},
                headers={"Origin": "http://localhost"},
            )
            self.assertEqual(response.status_code, 403, response.get_data(as_text=True))


class MaterialNavigationFrontend68Tests(unittest.TestCase):
    def source(self, relative_path):
        return ROOT.joinpath(relative_path).read_text(encoding="utf-8")

    def test_system_navigation_opens_materials_not_admin_workspace(self):
        html = self.source("static/system.html")
        core = self.source("static/system-core.js")
        self.assertIn('onclick="openTeachingMaterials()"', html)
        self.assertNotIn("onclick=\"openAdminWorkspace('course-materials')\"", html)
        self.assertIn("function openTeachingMaterials()", core)
        self.assertIn("switchLearningModule('materials')", core)
        self.assertIn('onclick="toggleAdminModal(true)"', html)

    def test_portal_navigation_uses_area_catalog_without_group_hardcoding(self):
        portal = self.source("static/portal-v56.js")
        self.assertIn("$$('.v575-manage-direct')", portal)
        self.assertIn("location.pathname==='/pgy'?'/pgy':'/internal'", portal)
        self.assertIn("['教材','/internal']", portal)

    def test_reader_error_contract_is_specific_and_login_is_safe(self):
        source = self.source("static/system-learner.js")
        for marker in (
            "error.status = res.status",
            "error.loginRequired",
            "登入已逾時，請",
            "重新登入",
            "沒有教材瀏覽權限",
            "教材服務暫時發生錯誤",
            "無法連線至伺服器",
            "encodeURIComponent(next)",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("Flask) 是否已啟動", source)

    def test_admin_secret_is_not_persisted_in_browser_storage(self):
        source = self.source("static/system-admin.js")
        self.assertNotIn("localStorage.setItem('admin_key'", source)
        self.assertNotIn("sessionStorage.setItem('admin_key'", source)


if __name__ == "__main__":
    unittest.main()
