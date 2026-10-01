import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.command_center import analytics
from teacher_app.common import db as common_db
from teacher_app.learning import progress_service


class CourseCompletionGoldenPathTests(unittest.TestCase):
    """GP-03: learner completion and teacher analytics must agree on one durable record."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "course-completion-golden-path.sqlite"
        conn, _ = self.connect()
        try:
            conn.execute(
                "CREATE TABLE material_progress ("
                "emp_id TEXT NOT NULL,name TEXT NOT NULL,material_id TEXT NOT NULL,"
                "completed_at TEXT NOT NULL,completed_version INTEGER NOT NULL DEFAULT 1,"
                "PRIMARY KEY(emp_id,material_id))"
            )
            conn.execute(
                "CREATE TABLE exam_records ("
                "id TEXT PRIMARY KEY,emp_id TEXT,training_area TEXT,group_key TEXT,created_at TEXT,"
                "answers_detail TEXT DEFAULT '[]',evaluator_name TEXT DEFAULT '',evaluator_title TEXT DEFAULT '',"
                "course_id TEXT DEFAULT '',review_status TEXT DEFAULT 'completed',reviewed_at TEXT DEFAULT '',"
                "reviewer_name TEXT DEFAULT '',review_comment TEXT DEFAULT '',quiz_category_id TEXT DEFAULT '',"
                "publication_id TEXT DEFAULT '',publication_hash TEXT DEFAULT '',passing_score INTEGER DEFAULT 80)"
            )
        finally:
            conn.close()

        self.user = {
            "username": "student-gp03",
            "empId": "S-GP03",
            "name": "學員 GP03",
            "role": "student",
            "preferredGroup": "grpBio",
        }
        self.material = {
            "id": "mat-gp03",
            "title": "GP03 教材",
            "courseId": "course-gp03",
            "area": "internal",
            "group": "grpBio",
            "active": True,
            "currentVersion": 1,
            "requiredCompletionVersion": 1,
        }
        self.course = {
            "id": "course-gp03",
            "title": "GP03 課程",
            "area": "internal",
            "group": "grpBio",
            "active": True,
            "completionPolicy": {"examMode": "none"},
        }

        patches = [
            patch.object(common_db, "get_connection", side_effect=self.connect),
            patch.object(analytics, "get_connection", side_effect=self.connect),
            patch.object(progress_service.material_repository, "get_material", return_value=self.material),
            patch.object(progress_service.material_repository, "list_uploaded_materials", return_value=[self.material]),
            patch.object(progress_service.course_repository, "list_courses", return_value=[self.course]),
            patch.object(progress_service.assessment_repository, "list_categories", return_value=[]),
            patch.object(progress_service.learning_access, "can_access_learning_item", return_value=True),
            patch.object(progress_service.learning_access, "can_access_requested_scope", return_value=True),
        ]
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

    def connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def test_learner_completion_becomes_teacher_visible_from_same_record(self):
        completed_at = progress_service.mark_material_complete(self.user, self.material["id"])
        self.assertTrue(completed_at)

        learner = progress_service.my_progress(
            self.user,
            area="internal",
            group="grpBio",
        )
        self.assertEqual(learner["materialsCompleted"][self.material["id"]], completed_at)
        self.assertEqual(len(learner["courses"]), 1)
        self.assertTrue(learner["courses"][0]["completed"])
        self.assertEqual(learner["courses"][0]["materialsCompleted"], 1)
        self.assertEqual(learner["courses"][0]["materialsTotal"], 1)

        legacy_rows = analytics.load_legacy_material_rows([self.user["empId"]])
        teacher_projection = analytics.project_analytics(
            {"kind": "group", "group": "grpBio"},
            [{**self.user, "group": "grpBio"}],
            [],
            legacy_rows,
            [],
            [],
            [],
        )
        self.assertEqual(teacher_projection["summary"]["materialsTracked"], 1)
        self.assertEqual(teacher_projection["summary"]["materialsCompleted"], 1)
        self.assertEqual(teacher_projection["summary"]["materialCompletionRate"], 100.0)
        self.assertEqual(teacher_projection["learners"][0]["materials"]["completed"], 1)
        self.assertEqual(teacher_projection["learners"][0]["materials"]["completionRate"], 100.0)

        conn, _ = self.connect()
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM material_progress WHERE emp_id=? AND material_id=?",
                (self.user["empId"], self.material["id"]),
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 1, "learner and teacher projections must share one durable completion row")


if __name__ == "__main__":
    unittest.main()
