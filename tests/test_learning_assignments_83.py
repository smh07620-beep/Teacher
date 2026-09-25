import sqlite3
import unittest
from unittest.mock import patch

import release_contract
import schema_migrations
from teacher_app.learning import assignment_service
from teacher_app.maintenance.learning_assignment_migration import learning_assignments_83


class LearningAssignment83Tests(unittest.TestCase):
    def test_release_registry_contains_0083_once(self):
        versions = [version for version, _fn in schema_migrations.MIGRATIONS]
        self.assertEqual(versions.count("0083-learning-assignments"), 1)
        self.assertIn("0083-learning-assignments", release_contract.REQUIRED_MIGRATIONS)
        self.assertLess(
            release_contract.REQUIRED_MIGRATIONS.index("0083-learning-assignments"),
            release_contract.REQUIRED_MIGRATIONS.index("0084-material-version-retraining"),
        )

    def test_sqlite_migration_is_additive_and_idempotent(self):
        conn = sqlite3.connect(":memory:")
        try:
            learning_assignments_83(conn, "sqlite")
            learning_assignments_83(conn, "sqlite")
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(learning_assignments)").fetchall()
            }
            self.assertTrue({
                "id", "course_id", "training_area", "group_key", "assignee_type",
                "assignee_key", "required", "due_at", "assigned_at", "assigned_by",
                "active", "created_at", "updated_at",
            }.issubset(columns))
            indexes = {
                row[1] for row in conn.execute("PRAGMA index_list(learning_assignments)").fetchall()
            }
            self.assertIn("idx_learning_assignments_assignee", indexes)
            self.assertIn("idx_learning_assignments_course", indexes)
            self.assertIn("idx_learning_assignments_due", indexes)
        finally:
            conn.close()

    def test_resolver_deduplicates_course_with_user_precedence_required_or_and_earliest_due(self):
        resolved = assignment_service.resolve_assignments([
            {
                "id": "all-1", "courseId": "course-1", "assigneeType": "all",
                "assigneeKey": "*", "required": False, "dueAt": "2026-10-30T00:00:00+00:00",
                "assignedAt": "2026-09-01T00:00:00+00:00", "assignedBy": "admin",
            },
            {
                "id": "group-1", "courseId": "course-1", "assigneeType": "group",
                "assigneeKey": "grpBio", "required": True, "dueAt": "2026-10-20T00:00:00+00:00",
                "assignedAt": "2026-09-02T00:00:00+00:00", "assignedBy": "leader",
            },
            {
                "id": "user-1", "courseId": "course-1", "assigneeType": "user",
                "assigneeKey": "student.bio", "required": False, "dueAt": "2026-10-25T00:00:00+00:00",
                "assignedAt": "2026-09-03T00:00:00+00:00", "assignedBy": "teacher",
            },
        ])
        self.assertEqual(len(resolved), 1)
        item = resolved[0]
        self.assertEqual(item["id"], "user-1")
        self.assertEqual(item["assigneeType"], "user")
        self.assertTrue(item["required"])
        self.assertEqual(item["dueAt"], "2026-10-20T00:00:00+00:00")
        self.assertEqual(set(item["sourceAssignmentIds"]), {"all-1", "group-1", "user-1"})

    @patch("teacher_app.learning.assignment_service.course_repository.get_course")
    def test_assignment_scope_is_snapshotted_from_course_not_browser(self, get_course):
        get_course.return_value = {
            "id": "course-1",
            "area": "internal",
            "group": "grpBio",
        }
        actor = {"username": "leader.bio"}
        item = assignment_service.build_assignment(actor, {
            "courseId": "course-1",
            "assigneeType": "group",
            "assigneeKey": "grpBio",
            "area": "pgy",
            "group": "grpMicro",
            "required": True,
            "dueAt": "2026-10-31T23:59:00+08:00",
        })
        self.assertEqual(item["training_area"], "internal")
        self.assertEqual(item["group_key"], "grpBio")
        self.assertEqual(item["assignee_key"], "grpBio")
        self.assertEqual(item["due_at"], "2026-10-31T15:59:00+00:00")

    @patch("teacher_app.learning.assignment_service.course_repository.get_course")
    def test_group_assignment_cannot_target_another_group(self, get_course):
        get_course.return_value = {
            "id": "course-1",
            "area": "internal",
            "group": "grpBio",
        }
        with self.assertRaises(Exception) as caught:
            assignment_service.build_assignment(
                {"username": "leader.bio"},
                {
                    "courseId": "course-1",
                    "assigneeType": "group",
                    "assigneeKey": "grpMicro",
                },
            )
        self.assertEqual(getattr(caught.exception, "status", None), 400)


if __name__ == "__main__":
    unittest.main()
