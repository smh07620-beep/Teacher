"""Regression coverage for the 6.8 post-release material-navigation fix."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as legacy_app
import pgy_app
import schema_migrations


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
        schema_migrations.apply_migrations(legacy_app)
        conn, _ = self.connect()
        try:
            conn.execute(
                "INSERT INTO user_accounts "
                "(username,password_hash,display_name,emp_id,role,preferred_area,preferred_group,active,session_version,created_at,updated_at,last_login_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "education-admin", generate_password_hash("test-password"),
                    "Education Admin", "E001", "education_admin", "internal", "grpHema",
                    1, 1, "2026-01-01", "2026-01-01", "",
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

    def login(self):
        response = self.client.post(
            "/api/auth/login",
            json={"username": "education-admin", "password": "test-password"},
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

    def test_material_mutations_still_require_elevation(self):
        self.login()
        for response in (
            self.client.get("/api/slides/admin"),
            self.client.patch("/api/slides/not-a-material", json={"title": "x"}, headers={"Origin": "http://localhost"}),
            self.client.delete("/api/slides/not-a-material", headers={"Origin": "http://localhost"}),
        ):
            self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
            self.assertTrue(response.get_json()["elevationRequired"])


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
