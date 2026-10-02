import datetime as dt
import sqlite3
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from teacher_app.command_center import teacher_learners
from teacher_app.command_center.routes import register_training_command_center
from teacher_app.common.errors import ApiError


NOW = dt.datetime(2026, 10, 2, 2, 0, tzinfo=dt.timezone.utc)


class TeacherLearnersP2Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE user_accounts(
                username TEXT PRIMARY KEY,
                display_name TEXT NOT NULL DEFAULT '',
                emp_id TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE pgy_assignments(
                id TEXT PRIMARY KEY,
                learner_username TEXT NOT NULL,
                teacher_username TEXT NOT NULL,
                training_area TEXT NOT NULL DEFAULT 'pgy',
                group_key TEXT NOT NULL,
                status TEXT NOT NULL,
                due_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );
            """
        )
        self.conn.executemany(
            "INSERT INTO user_accounts(username,display_name,emp_id,active) VALUES (?,?,?,1)",
            [
                ("student1", "生化學員", "S001"),
                ("student2", "血液學員", "S002"),
                ("student3", "生化學員乙", "S003"),
            ],
        )
        self.conn.executemany(
            """
            INSERT INTO pgy_assignments(
                id,learner_username,teacher_username,training_area,group_key,status,due_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            [
                ("a1", "student1", "teacher1", "pgy", "grpBio", "submitted", "2026-10-03T00:00:00+00:00", "2026-10-01T10:00:00+00:00"),
                ("a2", "student3", "teacher2", "pgy", "grpBio", "group_countersigned", "2026-10-01T00:00:00+00:00", "2026-10-01T11:00:00+00:00"),
                ("a3", "student2", "teacher2", "pgy", "grpBlood", "finalized", "2026-10-01T00:00:00+00:00", "2026-10-01T12:00:00+00:00"),
            ],
        )
        self.conn.commit()

        @contextmanager
        def reader():
            yield self.conn, "sqlite"

        self.reader = reader

    def tearDown(self):
        self.conn.close()

    def build(self, user):
        with patch.object(teacher_learners.common_db, "read_connection", self.reader):
            return teacher_learners.build_teacher_learners(user, now=NOW)

    def test_clinical_teacher_sees_only_explicitly_assigned_learners(self):
        data = self.build(
            {
                "username": "teacher1",
                "role": "clinical_teacher",
                "roles": ["clinical_teacher"],
                "preferredGroup": "grpBio",
            }
        )
        self.assertEqual(data["scope"]["kind"], "assigned")
        self.assertEqual([row["username"] for row in data["learners"]], ["student1"])
        self.assertEqual(data["summary"]["awaitingTeacher"], 1)

    def test_group_leader_sees_only_own_group(self):
        data = self.build(
            {
                "username": "leader1",
                "role": "group_leader",
                "roles": ["group_leader"],
                "preferredGroup": "grpBio",
            }
        )
        self.assertEqual(data["scope"], {"kind": "group", "group": "grpBio"})
        self.assertEqual(
            {row["username"] for row in data["learners"]},
            {"student1", "student3"},
        )
        self.assertEqual(data["summary"]["overdueAssignments"], 1)
        self.assertEqual(data["summary"]["awaitingFinalize"], 1)

    def test_education_admin_can_coordinate_cross_group_without_signing_projection(self):
        data = self.build(
            {
                "username": "edu1",
                "role": "education_admin",
                "roles": ["education_admin"],
                "preferredGroup": "grpBio",
            }
        )
        self.assertEqual(data["scope"]["kind"], "organization")
        self.assertEqual(
            {row["username"] for row in data["learners"]},
            {"student1", "student2", "student3"},
        )
        for row in data["learners"]:
            self.assertNotIn("canSign", row)
            self.assertNotIn("permissions", row)

    def test_system_admin_alone_does_not_gain_clinical_learner_scope(self):
        with self.assertRaises(ApiError) as caught:
            self.build(
                {
                    "username": "sys1",
                    "role": "system_admin",
                    "roles": ["system_admin"],
                    "preferredGroup": "grpBio",
                }
            )
        self.assertEqual(caught.exception.status, 403)

    def test_teacher_learners_route_is_get_only_and_session_scoped(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")
        user = {
            "username": "teacher1",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredGroup": "grpBio",
        }
        owner = SimpleNamespace(app=app, _current_user=lambda: user)
        register_training_command_center(owner)
        client = app.test_client()
        with patch.object(
            teacher_learners,
            "build_teacher_learners",
            return_value={"learners": [], "summary": {}, "scope": {"kind": "assigned"}},
        ) as build:
            response = client.get("/api/training-command-center/teacher-learners")
        self.assertEqual(response.status_code, 200)
        build.assert_called_once_with(user)
        self.assertEqual(
            client.post("/api/training-command-center/teacher-learners").status_code,
            405,
        )


if __name__ == "__main__":
    unittest.main()
