"""Behavioural coverage for session-scoped retry-safe Course Wizard bundles."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

import schema_migrations
from course_bundle_72 import (
    MIGRATION_ID,
    _course_bundle_idempotency_72,
    register_course_bundle_72,
)
from rbac_681 import _require_permission
from teacher_app.courses import bundle as canonical_bundle


class CourseBundle72Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = str(Path(self.tmp.name) / "bundle.sqlite")
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="course-bundle-test")
        self.current_user = None
        self.base = SimpleNamespace(
            app=self.app,
            DEFAULT_GROUP="grpBio",
            DEFAULT_TRAINING_AREA="internal",
            normalize_group=lambda value: value if value in {"grpBio", "grpHema"} else "grpBio",
            normalize_area=lambda value: value if value in {"internal", "pgy"} else "internal",
            _db_conn=self.connect,
            _current_user=lambda: self.current_user,
        )
        self.base.require_permission = lambda permission: _require_permission(self.base, permission)
        self.base.get_course = self.get_course
        self.base.get_quiz_category = self.get_quiz_category
        self._create_schema()
        self.canonical_db = patch(
            "teacher_app.common.db.get_connection",
            side_effect=self.connect,
        )
        self.canonical_db.start()
        self.addCleanup(self.canonical_db.stop)
        register_course_bundle_72(self.base)
        self.client = self.app.test_client()

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def _create_schema(self):
        conn, _ = self.connect()
        try:
            conn.execute(
                "CREATE TABLE courses (id TEXT PRIMARY KEY,training_area TEXT NOT NULL,group_key TEXT NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',sort_order INTEGER NOT NULL DEFAULT 0,date_added TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1)"
            )
            conn.execute(
                "CREATE TABLE quiz_categories (id TEXT PRIMARY KEY,group_key TEXT NOT NULL,training_area TEXT NOT NULL,course_id TEXT NOT NULL DEFAULT '',title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',sort_order INTEGER NOT NULL DEFAULT 0,date_added TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 0,draw_count INTEGER NOT NULL DEFAULT 0,passing_score INTEGER NOT NULL DEFAULT 80,audience TEXT NOT NULL DEFAULT '',draw_rules TEXT NOT NULL DEFAULT '{}',review_status TEXT NOT NULL DEFAULT 'draft',reviewer_name TEXT NOT NULL DEFAULT '',reviewed_at TEXT NOT NULL DEFAULT '',published_at TEXT NOT NULL DEFAULT '')"
            )
            _course_bundle_idempotency_72(conn, "sqlite")
        finally:
            conn.close()

    def get_course(self, course_id):
        conn, _ = self.connect()
        try:
            row = conn.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            return {
                "id": data["id"],
                "area": data["training_area"],
                "group": data["group_key"],
                "title": data["title"],
                "desc": data["description"],
                "active": bool(data["active"]),
            }
        finally:
            conn.close()

    def get_quiz_category(self, category_id):
        conn, _ = self.connect()
        try:
            row = conn.execute("SELECT * FROM quiz_categories WHERE id=?", (category_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            return {
                "id": data["id"],
                "group": data["group_key"],
                "area": data["training_area"],
                "courseId": data["course_id"],
                "title": data["title"],
                "desc": data["description"],
                "active": bool(data["active"]),
                "reviewStatus": data["review_status"],
            }
        finally:
            conn.close()

    def payload(self, workflow="cw-1234567890-abcd", **overrides):
        data = {
            "workflowId": workflow,
            "area": "pgy",
            "group": "grpHema",
            "title": "血液鏡檢基礎訓練",
            "desc": "PGY course",
            "examMode": "bank",
            "examTitle": "課後評量",
            "existingMaterialCount": 2,
            "uploadCount": 1,
        }
        data.update(overrides)
        return data

    def set_user(self, role, group="grpHema", username=None):
        self.current_user = {
            "username": username or role,
            "role": role,
            "roles": [role],
            "preferredGroup": group,
        }

    def counts(self):
        conn, _ = self.connect()
        try:
            return (
                conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
                conn.execute("SELECT COUNT(*) FROM quiz_categories").fetchone()[0],
                conn.execute("SELECT COUNT(*) FROM course_bundle_requests").fetchone()[0],
            )
        finally:
            conn.close()

    def test_migration_is_registered_and_idempotent(self):
        self.assertIn(MIGRATION_ID, [version for version, _fn in schema_migrations.MIGRATIONS])
        conn, _ = self.connect()
        try:
            _course_bundle_idempotency_72(conn, "sqlite")
            _course_bundle_idempotency_72(conn, "sqlite")
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        self.assertIn("course_bundle_requests", tables)

    def test_anonymous_student_and_auditor_cannot_create_bundle(self):
        response = self.client.post("/api/course-bundles", json=self.payload())
        self.assertEqual(response.status_code, 401)
        for role in ("student", "auditor"):
            self.set_user(role)
            response = self.client.post("/api/course-bundles", json=self.payload(workflow=f"cw-{role}-1234567890"))
            self.assertEqual(response.status_code, 403, role)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_group_scoped_teacher_cannot_create_cross_group_bundle(self):
        self.set_user("clinical_teacher", group="grpHema")
        response = self.client.post(
            "/api/course-bundles",
            json=self.payload(group="grpBio"),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_same_workflow_reuses_exact_course_and_exam(self):
        self.set_user("clinical_teacher")
        data = self.payload()
        first = self.client.post("/api/course-bundles", json=data)
        second = self.client.post("/api/course-bundles", json=data)
        self.assertEqual(first.status_code, 201, first.get_data(as_text=True))
        self.assertEqual(second.status_code, 200, second.get_data(as_text=True))
        one, two = first.get_json(), second.get_json()
        self.assertFalse(one["reused"])
        self.assertTrue(two["reused"])
        self.assertEqual(one["course"]["id"], two["course"]["id"])
        self.assertEqual(one["quizCategory"]["id"], two["quizCategory"]["id"])
        self.assertEqual(two["stages"]["course"], "reused")
        self.assertEqual(two["stages"]["exam"], "reused")
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_same_workflow_cannot_be_reused_for_changed_bundle(self):
        self.set_user("group_leader")
        data = self.payload(workflow="cw-conflict-1234567890")
        first = self.client.post("/api/course-bundles", json=data)
        changed = self.client.post("/api/course-bundles", json={**data, "title": "另一門課"})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(changed.get_json()["code"], "IDEMPOTENCY_KEY_REUSED")
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_later_mode_creates_only_course_and_education_admin_is_cross_group(self):
        self.set_user("education_admin", group="grpBio")
        response = self.client.post(
            "/api/course-bundles",
            json=self.payload(workflow="cw-later-1234567890", group="grpHema", examMode="later", examTitle=""),
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        body = response.get_json()
        self.assertIsNone(body["quizCategory"])
        self.assertEqual(body["stages"]["exam"], "skipped")
        self.assertEqual(self.counts(), (1, 0, 1))

    def test_failed_atomic_bundle_rolls_back_and_same_workflow_can_retry(self):
        self.set_user("clinical_teacher")
        data = self.payload(workflow="cw-rollback-1234567890")
        with patch.object(canonical_bundle, "_create_exam", side_effect=RuntimeError("simulated")):
            failed = self.client.post("/api/course-bundles", json=data)
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(self.counts(), (0, 0, 0))
        retried = self.client.post("/api/course-bundles", json=data)
        self.assertEqual(retried.status_code, 201, retried.get_data(as_text=True))
        self.assertEqual(self.counts(), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
