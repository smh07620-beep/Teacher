import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

import release_contract
import schema_migrations
from teacher_app.common.auth import ROLE_PERMISSIONS
from teacher_app.maintenance import announcement_schema
from teacher_app.maintenance.announcement_routes import register_announcement_routes


ROOT = Path(__file__).resolve().parents[1]


class _Owner:
    def __init__(self, app):
        self.app = app
        self.user = None

    def _current_user(self):
        return self.user


class AnnouncementWorkspace116Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "announcements.db"
        conn, kind = self._connect()
        try:
            announcement_schema.init_schema(conn, kind)
            conn.commit()
        finally:
            conn.close()

        self.db_patch = patch(
            "teacher_app.common.db.get_connection",
            side_effect=self._connect,
        )
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="announcement-test")
        self.owner = _Owner(self.app)
        register_announcement_routes(self.owner)
        self.client = self.app.test_client()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def test_migration_and_permissions_are_explicit(self):
        versions = [version for version, _fn in schema_migrations.MIGRATIONS]
        self.assertEqual(versions.count("0116-announcement-audience"), 1)
        self.assertEqual(release_contract.REQUIRED_MIGRATIONS[-1], "0116-announcement-audience")
        for role in ("clinical_teacher", "group_leader", "education_admin", "system_admin"):
            self.assertIn("announcement.manage", ROLE_PERMISSIONS[role])
        self.assertNotIn("announcement.manage", ROLE_PERMISSIONS["student"])
        self.assertNotIn("announcement.manage", ROLE_PERMISSIONS["auditor"])

    def test_group_scoped_teacher_cannot_publish_cross_group_or_system_notice(self):
        self.owner.user = {
            "username": "teacher-bio",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }
        own = self.client.post(
            "/api/announcements",
            json={
                "kind": "teaching",
                "scopeType": "group",
                "group": "grpBio",
                "title": "生化組通知",
            },
        )
        self.assertEqual(own.status_code, 201, own.get_json())
        self.assertEqual(own.get_json()["group"], "grpBio")
        self.assertEqual(own.get_json()["kind"], "teaching")

        cross = self.client.post(
            "/api/announcements",
            json={
                "kind": "teaching",
                "scopeType": "group",
                "group": "grpHema",
                "title": "跨組",
            },
        )
        self.assertEqual(cross.status_code, 403)

        global_notice = self.client.post(
            "/api/announcements",
            json={"kind": "teaching", "scopeType": "all", "title": "全院"},
        )
        self.assertEqual(global_notice.status_code, 403)

        system_notice = self.client.post(
            "/api/announcements",
            json={"kind": "system", "title": "維護"},
        )
        self.assertEqual(system_notice.status_code, 403)

    def test_multi_role_teacher_with_education_admin_keeps_cross_group_scope(self):
        self.owner.user = {
            "username": "dual-admin",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher", "education_admin"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }
        response = self.client.post(
            "/api/announcements",
            json={
                "kind": "teaching",
                "scopeType": "group",
                "area": "internal",
                "group": "grpHema",
                "title": "跨組教學公告",
            },
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["group"], "grpHema")

    def test_education_admin_can_publish_cross_group_teaching_notice(self):
        self.owner.user = {
            "username": "edu",
            "role": "education_admin",
            "roles": ["education_admin"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }
        response = self.client.post(
            "/api/announcements",
            json={
                "kind": "teaching",
                "scopeType": "all",
                "title": "院內教育訓練通知",
                "pinned": True,
            },
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["scopeType"], "all")
        self.assertTrue(response.get_json()["pinned"])

    def test_system_admin_owns_system_notice_and_public_feed_is_personalized(self):
        self.owner.user = {
            "username": "root",
            "role": "system_admin",
            "roles": ["system_admin"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }
        system_notice = self.client.post(
            "/api/announcements",
            json={"kind": "system", "title": "系統維護"},
        )
        self.assertEqual(system_notice.status_code, 201, system_notice.get_json())

        bio = self.client.post(
            "/api/announcements",
            json={
                "kind": "teaching",
                "scopeType": "group",
                "area": "internal",
                "group": "grpBio",
                "title": "生化組公告",
            },
        )
        self.assertEqual(bio.status_code, 201, bio.get_json())
        hema = self.client.post(
            "/api/announcements",
            json={
                "kind": "teaching",
                "scopeType": "group",
                "area": "internal",
                "group": "grpHema",
                "title": "血液組公告",
            },
        )
        self.assertEqual(hema.status_code, 201, hema.get_json())

        self.owner.user = {
            "username": "student-bio",
            "role": "student",
            "roles": ["student"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }
        visible = self.client.get("/api/announcements?limit=20")
        self.assertEqual(visible.status_code, 200)
        titles = {item["title"] for item in visible.get_json()}
        self.assertIn("系統維護", titles)
        self.assertIn("生化組公告", titles)
        self.assertNotIn("血液組公告", titles)

    def test_ui_moves_teaching_announcements_out_of_static_system_management(self):
        html = ROOT.joinpath("static/system.html").read_text(encoding="utf-8")
        ui = ROOT.joinpath("static/admin-announcements.js").read_text(encoding="utf-8")
        teacher = ROOT.joinpath("static/teacher-workspace-1014.js").read_text(encoding="utf-8")
        workspace = ROOT.joinpath("static/admin-workspace.js").read_text(encoding="utf-8")

        self.assertNotIn("admin-announcement-title", html)
        self.assertNotIn(">首頁公告<", html)
        self.assertIn("teacher-announcement-workspace-1014", ui)
        self.assertIn("system-announcement-card-1014", ui)
        self.assertIn("/api/announcements/admin?kind=", ui)
        self.assertIn("Email 通知仍由既有課程／考核提醒排程負責", ui)
        self.assertIn("teacher-announcements-open-1014", teacher)
        self.assertIn("openAnnouncements", teacher)
        self.assertIn("renderAdminAnnouncements?.('system')", workspace)


if __name__ == "__main__":
    unittest.main()
