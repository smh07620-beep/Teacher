"""2026-10-09: 組長／臨床教師只能管理自己組別的考卷；管理者跨組；學生不能寫入。
以真實 create_app() 與拋棄式 SQLite 實測，不用 mock 權限。"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import flask.testing
from werkzeug.security import generate_password_hash

from teacher_app.factory import create_app

PASSWORD = "pw-123456"
USERS = [
    ("admin1", "education_admin"),
    ("sys1", "system_admin"),
    ("leaderbio", "group_leader"),
    ("teacherbio", "clinical_teacher"),
    ("stubio", "student"),
]


class ExamGroupScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        path = str(Path(cls.temp.name) / "scope.sqlite")

        def connect():
            conn = sqlite3.connect(path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.isolation_level = None
            return conn, "sqlite"

        cls.db_patch = patch("teacher_app.common.db.get_connection", side_effect=connect)
        cls.db_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls._orig_open = flask.testing.FlaskClient.open

        def open_with_origin(self, *args, **kwargs):
            headers = dict(kwargs.get("headers") or {})
            headers.setdefault("Origin", "http://localhost")
            kwargs["headers"] = headers
            return cls._orig_open(self, *args, **kwargs)

        flask.testing.FlaskClient.open = open_with_origin
        password_hash = generate_password_hash(PASSWORD, method="pbkdf2:sha256:1000")
        conn, _kind = connect()
        for username, role in USERS:
            conn.execute(
                "INSERT INTO user_accounts (username,password_hash,display_name,emp_id,role,preferred_area,"
                "preferred_group,active,session_version,created_at,updated_at,last_login_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (username, password_hash, username, "E" + username, role, "internal", "grpBio", 1, 1, "c", "u", ""),
            )
        conn.close()
        admin = cls.login("admin1")
        cls.ids = {}
        for group in ("grpBio", "grpHema"):
            response = admin.post("/api/quiz-categories", json={"title": "exam-" + group, "group": group, "area": "internal"})
            assert response.status_code == 200, response.get_data(as_text=True)
            cls.ids[group] = response.get_json()["id"]

    @classmethod
    def tearDownClass(cls):
        flask.testing.FlaskClient.open = cls._orig_open
        cls.db_patch.stop()
        cls.temp.cleanup()

    @classmethod
    def login(cls, username):
        client = cls.app.test_client()
        response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
        assert response.status_code == 200, (username, response.get_data(as_text=True))
        return client

    def test_group_scoped_roles_cannot_touch_another_groups_exam(self):
        other = self.ids["grpHema"]
        for username in ("leaderbio", "teacherbio"):
            client = self.login(username)
            self.assertEqual(client.get("/api/quiz-categories/" + other).status_code, 403, username)
            self.assertEqual(client.patch("/api/quiz-categories/" + other, json={"title": "x"}).status_code, 403, username)
            self.assertEqual(client.post(f"/api/quiz-categories/{other}/publish", json={}).status_code, 403, username)
            self.assertEqual(client.delete("/api/quiz-categories/" + other).status_code, 403, username)
            self.assertEqual(client.post("/api/quiz-categories", json={"title": "x", "group": "grpHema", "area": "internal"}).status_code, 403, username)
            listing = client.get("/api/quiz-categories/admin?group=grpHema&area=internal")
            self.assertEqual([item["title"] for item in listing.get_json()], [], username)
            unscoped = client.get("/api/quiz-categories/admin?area=internal").get_json()
            self.assertNotIn("exam-grpHema", [item["title"] for item in unscoped], username)

    def test_group_scoped_roles_can_manage_their_own_group(self):
        own = self.ids["grpBio"]
        for username in ("leaderbio", "teacherbio"):
            client = self.login(username)
            self.assertEqual(client.get("/api/quiz-categories/" + own).status_code, 200, username)

    def test_admins_manage_every_group(self):
        for username in ("admin1", "sys1"):
            client = self.login(username)
            for group in ("grpBio", "grpHema"):
                self.assertEqual(client.get("/api/quiz-categories/" + self.ids[group]).status_code, 200, (username, group))

    def test_student_cannot_manage_exams(self):
        client = self.login("stubio")
        for group in ("grpBio", "grpHema"):
            exam = self.ids[group]
            self.assertEqual(client.get("/api/quiz-categories/admin?group=%s&area=internal" % group).status_code, 403)
            self.assertEqual(client.patch("/api/quiz-categories/" + exam, json={"title": "x"}).status_code, 403)
            self.assertEqual(client.post(f"/api/quiz-categories/{exam}/publish", json={}).status_code, 403)
            self.assertEqual(client.delete("/api/quiz-categories/" + exam).status_code, 403)


if __name__ == "__main__":
    unittest.main()
