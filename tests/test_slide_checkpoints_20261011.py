"""Optional in-slide checkpoint questions: RBAC, secrecy, one-answer rule."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as legacy_app
import pgy_app
from teacher_app.checkpoints import service
from teacher_app.maintenance.slide_checkpoint_migration import slide_checkpoints_118

ORIGIN = {"Origin": "http://localhost"}


class SlideCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "checkpoints.sqlite"
        for target in (
            patch.object(legacy_app, "_db_conn", self.connect),
            patch("teacher_app.common.db.get_connection", side_effect=self.connect),
        ):
            target.start()
            self.addCleanup(target.stop)
        legacy_app.init_user_accounts_db()
        legacy_app.init_exam_db()
        legacy_app.init_materials_db()
        legacy_app.init_quiz_db()
        legacy_app.init_learning_db()
        conn, kind = self.connect()
        try:
            conn.execute(
                "CREATE TABLE admin_elevations (username TEXT PRIMARY KEY, elevated_at TEXT NOT NULL, "
                "expires_at TEXT NOT NULL, session_version INTEGER NOT NULL DEFAULT 0)"
            )
            slide_checkpoints_118(conn, kind)
            for username, role, group in (
                ("education-admin", "education_admin", "grpHema"),
                ("clinical-teacher", "clinical_teacher", "grpHema"),
                ("other-teacher", "clinical_teacher", "grpBio"),
                ("student-user", "student", "grpHema"),
                ("student-other", "student", "grpBio"),
                ("auditor-user", "auditor", "grpHema"),
            ):
                conn.execute(
                    "INSERT INTO user_accounts "
                    "(username,password_hash,display_name,emp_id,role,preferred_area,preferred_group,active,session_version,created_at,updated_at,last_login_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (username, generate_password_hash("test-password"), username, f"E{abs(hash(username)) % 100000:05d}", role,
                     "internal", group, 1, 1, "2026-01-01", "2026-01-01", ""),
                )
        finally:
            conn.close()
        self.material = {
            "id": "mat-1", "group": "grpHema", "area": "internal", "active": True,
            "viewerMode": "slides", "pageCount": 10, "currentVersion": 1,
        }
        patcher = patch("teacher_app.materials.repository.get_material", side_effect=lambda mid: self.material if mid == "mat-1" else None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = pgy_app.app.test_client()

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def login(self, username):
        response = self.client.post("/api/auth/login", json={"username": username, "password": "test-password"}, headers=ORIGIN)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def body(self, **over):
        data = {"page": 3, "question": "此步驟的目的？", "options": ["稀釋", "固定", "染色"], "correctIndex": 1, "explanation": "固定細胞形態"}
        data.update(over)
        return data

    def create(self, **over):
        self.login("clinical-teacher")
        response = self.client.post("/api/materials/mat-1/checkpoints", json=self.body(**over), headers=ORIGIN)
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["item"]["id"]

    # --- authoring permissions
    def test_students_and_auditors_cannot_author(self):
        for username in ("student-user", "auditor-user"):
            self.login(username)
            r = self.client.post("/api/materials/mat-1/checkpoints", json=self.body(), headers=ORIGIN)
            self.assertEqual(r.status_code, 403, username)

    def test_teacher_of_another_group_cannot_author_or_delete(self):
        cid = self.create()
        self.login("other-teacher")
        self.assertEqual(self.client.post("/api/materials/mat-1/checkpoints", json=self.body(), headers=ORIGIN).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/slide-checkpoints/{cid}", headers=ORIGIN).status_code, 403)
        self.assertEqual(self.client.get("/api/materials/mat-1/checkpoints/manage").status_code, 403)

    def test_validation_gives_readable_errors(self):
        self.login("clinical-teacher")
        for bad in (
            {"page": 0}, {"page": 11}, {"page": "x"}, {"question": " "},
            {"options": ["only"]}, {"options": ["a", ""]}, {"correctIndex": 9}, {"correctIndex": None},
        ):
            with self.subTest(bad=bad):
                r = self.client.post("/api/materials/mat-1/checkpoints", json=self.body(**bad), headers=ORIGIN)
                self.assertEqual(r.status_code, 400, r.get_data(as_text=True))
                self.assertTrue(r.get_json()["error"])

    def test_non_slide_material_is_rejected(self):
        self.material["viewerMode"] = "video"
        self.login("clinical-teacher")
        r = self.client.post("/api/materials/mat-1/checkpoints", json=self.body(), headers=ORIGIN)
        self.assertEqual(r.status_code, 400)

    # --- learner side: secrecy until answered
    def test_learner_list_hides_answer_until_answered(self):
        cid = self.create()
        self.login("student-user")
        items = self.client.get("/api/materials/mat-1/checkpoints").get_json()["items"]
        self.assertEqual(len(items), 1)
        text = str(items[0])
        for secret in ("correctIndex", "explanation", "固定細胞形態"):
            self.assertNotIn(secret, text)
        self.assertEqual(items[0]["page"], 3)
        r = self.client.post(f"/api/slide-checkpoints/{cid}/answer", json={"chosenIndex": 0}, headers=ORIGIN)
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertFalse(data["isCorrect"])
        self.assertEqual(data["correctIndex"], 1)
        self.assertEqual(data["explanation"], "固定細胞形態")

    def test_first_answer_is_the_record_and_repeat_does_not_change_it(self):
        cid = self.create()
        self.login("student-user")
        first = self.client.post(f"/api/slide-checkpoints/{cid}/answer", json={"chosenIndex": 0}, headers=ORIGIN).get_json()
        second = self.client.post(f"/api/slide-checkpoints/{cid}/answer", json={"chosenIndex": 1}, headers=ORIGIN).get_json()
        self.assertFalse(first["isCorrect"])
        self.assertFalse(second["isCorrect"])
        self.assertEqual(second["chosenIndex"], 0)
        listing = self.client.get("/api/materials/mat-1/checkpoints").get_json()["items"][0]
        self.assertTrue(listing["answered"])

    def test_bad_choices_are_rejected(self):
        cid = self.create()
        self.login("student-user")
        for bad in (None, "x", 7, -1, True):
            r = self.client.post(f"/api/slide-checkpoints/{cid}/answer", json={"chosenIndex": bad}, headers=ORIGIN)
            self.assertEqual(r.status_code, 400, bad)

    def test_auditor_is_read_only_and_other_group_learner_cannot_see_material(self):
        cid = self.create()
        self.login("auditor-user")
        self.assertEqual(self.client.post(f"/api/slide-checkpoints/{cid}/answer", json={"chosenIndex": 1}, headers=ORIGIN).status_code, 403)
        self.login("student-other")
        self.assertEqual(self.client.get("/api/materials/mat-1/checkpoints").status_code, 404)
        self.assertEqual(self.client.post(f"/api/slide-checkpoints/{cid}/answer", json={"chosenIndex": 1}, headers=ORIGIN).status_code, 404)

    def test_anonymous_is_401(self):
        self.assertEqual(self.client.get("/api/materials/mat-1/checkpoints").status_code, 401)

    # --- opt-in behaviour and lifecycle
    def test_no_checkpoints_means_nothing_changes(self):
        self.login("student-user")
        self.assertEqual(self.client.get("/api/materials/mat-1/checkpoints").get_json(), {"items": []})

    def test_disabled_and_stale_checkpoints_are_hidden_from_learners(self):
        cid = self.create()
        self.login("clinical-teacher")
        self.client.patch(f"/api/slide-checkpoints/{cid}", json={"active": False}, headers=ORIGIN)
        self.login("student-user")
        self.assertEqual(self.client.get("/api/materials/mat-1/checkpoints").get_json()["items"], [])
        self.login("clinical-teacher")
        self.client.patch(f"/api/slide-checkpoints/{cid}", json={"active": True}, headers=ORIGIN)
        self.material["currentVersion"] = 2  # a new version of the slides replaces the pages
        self.login("student-user")
        self.assertEqual(self.client.get("/api/materials/mat-1/checkpoints").get_json()["items"], [])
        self.assertEqual(self.client.post(f"/api/slide-checkpoints/{cid}/answer", json={"chosenIndex": 1}, headers=ORIGIN).status_code, 404)
        self.login("clinical-teacher")
        listing = self.client.get("/api/materials/mat-1/checkpoints/manage").get_json()["items"][0]
        self.assertTrue(listing["stale"])

    def test_manager_sees_answer_key_and_stats(self):
        cid = self.create()
        self.login("student-user")
        self.client.post(f"/api/slide-checkpoints/{cid}/answer", json={"chosenIndex": 1}, headers=ORIGIN)
        self.login("clinical-teacher")
        item = self.client.get("/api/materials/mat-1/checkpoints/manage").get_json()["items"][0]
        self.assertEqual(item["correctIndex"], 1)
        self.assertEqual(item["stats"], {"answered": 1, "correct": 1})

    def test_edit_validates_and_delete_keeps_answers(self):
        cid = self.create()
        self.login("clinical-teacher")
        bad = self.client.patch(f"/api/slide-checkpoints/{cid}", json={"correctIndex": 8}, headers=ORIGIN)
        self.assertEqual(bad.status_code, 400)
        good = self.client.patch(f"/api/slide-checkpoints/{cid}", json={"question": "新題目", "page": 5}, headers=ORIGIN)
        self.assertEqual(good.get_json()["item"]["question"], "新題目")
        self.assertEqual(good.get_json()["item"]["page"], 5)
        self.assertEqual(self.client.delete(f"/api/slide-checkpoints/{cid}", headers=ORIGIN).status_code, 200)
        self.assertEqual(self.client.get("/api/materials/mat-1/checkpoints/manage").get_json()["items"], [])

    def test_per_material_limit(self):
        self.login("clinical-teacher")
        for _ in range(service.MAX_PER_MATERIAL):
            self.assertEqual(self.client.post("/api/materials/mat-1/checkpoints", json=self.body(), headers=ORIGIN).status_code, 201)
        over = self.client.post("/api/materials/mat-1/checkpoints", json=self.body(), headers=ORIGIN)
        self.assertEqual(over.status_code, 400)


if __name__ == "__main__":
    unittest.main()
