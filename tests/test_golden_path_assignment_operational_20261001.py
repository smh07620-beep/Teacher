import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.common import db as common_db
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.courses import schema as course_schema
from teacher_app.learning import assignment_routes, assignment_service
from teacher_app.maintenance.learning_assignment_migration import learning_assignments_83


class AssignmentGoldenPathOperationalTests(unittest.TestCase):
    """GP-02: assignment intent must become the correct learner-visible outcome."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "assignment-golden-path.sqlite"
        db_patch = patch.object(common_db, "get_connection", self.connect)
        db_patch.start()
        self.addCleanup(db_patch.stop)

        conn, kind = self.connect()
        try:
            course_schema.init_schema(conn, kind)
            learning_assignments_83(conn, kind)
        finally:
            conn.close()

        course_repository.create_course(
            course_id="course-bio-all",
            area="internal",
            group="grpBio",
            title="生化組 Golden Path 課程",
            description="驗證組長全體指派仍受課程 scope 約束",
            date_added=dt.datetime.now(dt.timezone.utc).isoformat(),
        )
        course_repository.create_course(
            course_id="course-micro-cross-scope",
            area="internal",
            group="grpMicro",
            title="細菌組跨組拒絕課程",
            description="cross-scope negative control",
            date_added=dt.datetime.now(dt.timezone.utc).isoformat(),
        )

        self.leader = {
            "username": "leader.bio",
            "role": "group_leader",
            "roles": ["group_leader"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }
        self.bio_student = {
            "username": "student.bio",
            "role": "student",
            "roles": ["student"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }
        self.micro_student = {
            "username": "student.micro",
            "role": "student",
            "roles": ["student"],
            "preferredArea": "internal",
            "preferredGroup": "grpMicro",
        }

    def connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def test_gp02_group_leader_all_means_everyone_in_course_group_only(self):
        # UI/API adapter intentionally offers the human-friendly "全體人員" choice.
        options = assignment_routes._audience_options_for_actor(
            self.leader,
            {
                "area": "internal",
                "group": "grpBio",
                "groups": [{"key": "grpBio", "label": "生化"}],
                "people": [],
                "allowedAssigneeTypes": ["group", "user"],
            },
        )
        self.assertIn("all", options["allowedAssigneeTypes"])
        self.assertEqual(options["allScope"], "course_group")

        # The adapter must convert "all" into a group-scoped persistence intent;
        # no organization-wide '*' assignment is allowed for a plain group leader.
        normalized = assignment_routes._normalize_create_payload(
            self.leader,
            {
                "courseId": "course-bio-all",
                "assigneeType": "all",
                "assigneeKey": "",
                "required": True,
                "dueAt": "2026-10-31T23:59:00+08:00",
            },
        )
        self.assertEqual(normalized["assigneeType"], "group")
        self.assertEqual(normalized["assigneeKey"], "")

        with patch(
            "teacher_app.learning.assignment_service.auth_accounts.list_accounts",
            return_value=[self.bio_student, self.micro_student, self.leader],
        ):
            created = assignment_service.create_assignment(self.leader, normalized)

        self.assertEqual(created["courseId"], "course-bio-all")
        self.assertEqual(created["area"], "internal")
        self.assertEqual(created["group"], "grpBio")
        self.assertEqual(created["assigneeType"], "group")
        self.assertEqual(created["assigneeKey"], "grpBio")
        self.assertNotEqual(created["assigneeKey"], "*")

        # Human-visible outcome: same-scope learner sees it; another group does not.
        bio_mine = assignment_service.mine(self.bio_student)
        micro_mine = assignment_service.mine(self.micro_student)
        self.assertEqual([item["courseId"] for item in bio_mine], ["course-bio-all"])
        self.assertEqual(micro_mine, [])
        self.assertTrue(bio_mine[0]["required"])
        self.assertEqual(bio_mine[0]["assigneeType"], "group")

    def test_gp02_group_leader_cannot_turn_all_into_cross_group_assignment(self):
        normalized = assignment_routes._normalize_create_payload(
            self.leader,
            {
                "courseId": "course-micro-cross-scope",
                "assigneeType": "all",
                "assigneeKey": "",
                "required": True,
            },
        )
        self.assertEqual(normalized["assigneeType"], "group")

        with self.assertRaises(ApiError) as caught:
            assignment_service.create_assignment(self.leader, normalized)
        self.assertEqual(caught.exception.code, "ASSIGNMENT_SCOPE_DENIED")
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(assignment_service.mine(self.micro_student), [])


if __name__ == "__main__":
    unittest.main()
