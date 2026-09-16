import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask, jsonify

import course_bundle_followup_73 as followup
from schema_migrations import MIGRATIONS


ROOT = Path(__file__).parents[1]
WORKFLOW_ID = "cw-test-workflow-0001"


class _Base:
    DEFAULT_GROUP = "grpBio"
    DEFAULT_TRAINING_AREA = "pgy"

    def __init__(self, db_path):
        self.db_path = db_path
        self.app = Flask(__name__ + str(id(self)))
        self.app.config.update(TESTING=True, SECRET_KEY="followup-test")
        self.user = {"username": "teacher1", "role": "clinical_teacher", "preferredGroup": "grpBio"}
        self.denied = None

    def _db_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def _current_user(self):
        return self.user

    def require_admin(self):
        return self.denied

    @staticmethod
    def normalize_group(value):
        return value if value in {"grpBio", "grpHema"} else "grpBio"

    @staticmethod
    def normalize_area(value):
        return value if value in {"pgy", "internal"} else "pgy"


class CourseBundleFollowup73Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        temp.close()
        self.path = temp.name
        self.addCleanup(Path(self.path).unlink, missing_ok=True)
        self.base = _Base(self.path)
        self.upload_calls = 0
        self.link_calls = 0

        @self.base.app.post("/api/material-jobs/upload", endpoint="api_enqueue_material_job")
        def upload():
            self.upload_calls += 1
            return jsonify({"jobId": f"job-{self.upload_calls}", "status": "pending"}), 202

        @self.base.app.patch("/api/slides/<slide_id>", endpoint="api_update_slide")
        def link(slide_id):
            self.link_calls += 1
            return jsonify({"id": slide_id, "courseId": "course-1"})

        conn, kind = self.base._db_conn()
        try:
            conn.execute(
                "CREATE TABLE course_bundle_requests ("
                "username TEXT NOT NULL,workflow_id TEXT NOT NULL,status TEXT NOT NULL,"
                "course_id TEXT NOT NULL,quiz_category_id TEXT NOT NULL,"
                "training_area TEXT NOT NULL,group_key TEXT NOT NULL,"
                "PRIMARY KEY(username,workflow_id))"
            )
            conn.execute(
                "INSERT INTO course_bundle_requests VALUES (?,?,?,?,?,?,?)",
                ("teacher1", WORKFLOW_ID, "completed", "course-1", "cat-1", "pgy", "grpBio"),
            )
            followup._course_bundle_followups_73(conn, kind)
            followup._course_bundle_followups_73(conn, kind)
        finally:
            conn.close()
        followup.register_course_bundle_followup_73(self.base)
        self.client = self.base.app.test_client()

    def upload_data(self, *, title="Lesson", size="17"):
        return {
            "file": (io.BytesIO(b"%PDF-1.4\nminimal"), "lesson.pdf"),
            "title": title,
            "group": "grpBio",
            "area": "pgy",
            "courseId": "course-1",
            "category": "cat-1",
            "materialType": "auto",
            "bundleWorkflowId": WORKFLOW_ID,
            "bundleFileIndex": "0",
            "bundleFileSize": size,
            "bundleFileLastModified": "123456789",
        }

    def link_payload(self, *, course_id="course-1"):
        return {
            "title": "Existing material",
            "courseId": course_id,
            "category": "cat-1",
            "group": "grpBio",
            "area": "pgy",
            "bundleWorkflowId": WORKFLOW_ID,
            "bundleLinkKey": "mat-1",
        }

    def test_migration_is_registered_once_and_idempotent(self):
        self.assertEqual([v for v, _fn in MIGRATIONS].count(followup.MIGRATION_ID), 1)
        conn, _ = self.base._db_conn()
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(course_bundle_followups)").fetchall()}
        finally:
            conn.close()
        self.assertTrue({"username", "workflow_id", "item_key", "request_hash", "status", "response_json"}.issubset(columns))

    def test_upload_retry_returns_same_job_without_second_queue_insert(self):
        first = self.client.post("/api/material-jobs/upload", data=self.upload_data(), content_type="multipart/form-data")
        second = self.client.post("/api/material-jobs/upload", data=self.upload_data(), content_type="multipart/form-data")
        self.assertEqual(first.status_code, 202, first.get_data(as_text=True))
        self.assertEqual(second.status_code, 200, second.get_data(as_text=True))
        self.assertEqual(first.get_json()["jobId"], second.get_json()["jobId"])
        self.assertFalse(first.get_json()["reused"])
        self.assertTrue(second.get_json()["reused"])
        self.assertEqual(self.upload_calls, 1)

    def test_same_upload_key_with_changed_metadata_is_rejected(self):
        first = self.client.post("/api/material-jobs/upload", data=self.upload_data(), content_type="multipart/form-data")
        changed = self.client.post("/api/material-jobs/upload", data=self.upload_data(title="Different"), content_type="multipart/form-data")
        self.assertEqual(first.status_code, 202)
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(changed.get_json()["code"], "FOLLOWUP_KEY_REUSED")
        self.assertEqual(self.upload_calls, 1)

    def test_existing_material_link_retry_is_idempotent(self):
        first = self.client.patch("/api/slides/mat-1", json=self.link_payload())
        second = self.client.patch("/api/slides/mat-1", json=self.link_payload())
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(first.get_json()["reused"])
        self.assertTrue(second.get_json()["reused"])
        self.assertEqual(self.link_calls, 1)

    def test_followup_cannot_target_another_course(self):
        response = self.client.patch("/api/slides/mat-1", json=self.link_payload(course_id="course-2"))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "FOLLOWUP_BUNDLE_MISMATCH")
        self.assertEqual(self.link_calls, 0)

    def test_legacy_calls_without_bundle_keys_keep_original_behavior(self):
        upload = self.client.post(
            "/api/material-jobs/upload",
            data={"file": (io.BytesIO(b"x"), "legacy.txt")},
            content_type="multipart/form-data",
        )
        link = self.client.patch("/api/slides/mat-1", json={"courseId": "legacy-course"})
        self.assertEqual(upload.status_code, 202)
        self.assertEqual(link.status_code, 200)
        self.assertEqual(self.upload_calls, 1)
        self.assertEqual(self.link_calls, 1)


class CourseBundleFollowup73Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = ROOT.joinpath("pgy_app.py").read_text(encoding="utf-8")
        cls.health = ROOT.joinpath("health_65.py").read_text(encoding="utf-8")
        cls.wizard = ROOT.joinpath("static", "course-wizard-681.js").read_text(encoding="utf-8")
        cls.adapter = ROOT.joinpath("course_bundle_followup_73.py").read_text(encoding="utf-8")

    def test_migration_imports_before_runner_and_adapter_registers_after_rbac(self):
        self.assertLess(self.entry.index("from course_bundle_followup_73"), self.entry.index("from schema_migrations"))
        self.assertLess(self.entry.index("register_rbac_681(legacy_app)"), self.entry.index("register_course_bundle_followup_73(legacy_app)"))
        self.assertIn("0073-course-bundle-followups", self.health)

    def test_wizard_sends_stable_keys_for_link_and_upload_followups(self):
        for marker in (
            "bundleWorkflowId:bundlePayload.workflowId",
            "bundleLinkKey:String(id)",
            "form.append('bundleFileIndex',String(index))",
            "form.append('bundleFileSize',String(file.size||0))",
            "form.append('bundleFileLastModified',String(file.lastModified||0))",
        ):
            self.assertIn(marker, self.wizard)

    def test_followup_adapter_uses_session_rbac_and_no_admin_key(self):
        self.assertIn("base.require_admin()", self.adapter)
        self.assertNotIn("X-Admin-Key", self.adapter)
        self.assertNotIn("getAdminKey", self.adapter)
        self.assertNotIn("elevation", self.adapter.lower())


if __name__ == "__main__":
    unittest.main()
