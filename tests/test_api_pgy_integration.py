import os
import tempfile
import unittest
from pathlib import Path

from flask import g

from teacher_app import create_app
from teacher_app.common.db import (
    execute,
    transaction,
)
from teacher_app.pgy import (
    repository as repo,
)


class PgyApiIntegrationTests(
    unittest.TestCase
):
    def setUp(self):
        handle, path = tempfile.mkstemp(
            suffix=".db"
        )
        os.close(handle)

        self.db_path = Path(path)

        self.old_database_url = (
            os.environ.pop(
                "DATABASE_URL",
                None,
            )
        )

        self.old_sqlite = os.environ.get(
            "TEACHER_SQLITE_PATH"
        )

        os.environ[
            "TEACHER_SQLITE_PATH"
        ] = str(self.db_path)

        with transaction() as (
            conn,
            kind,
        ):
            repo.init_schema(
                conn,
                kind,
            )

            self.insert_user(
                conn,
                "student1",
                "學員一",
                "S001",
                "student",
                "grpBio",
            )

            self.insert_user(
                conn,
                "student2",
                "學員二",
                "S002",
                "student",
                "grpBio",
            )

            self.insert_user(
                conn,
                "teacher1",
                "教師一",
                "T001",
                "clinical_teacher",
                "grpBio",
            )

            self.insert_user(
                conn,
                "teacher2",
                "教師二",
                "T002",
                "clinical_teacher",
                "grpBio",
            )

            self.insert_user(
                conn,
                "leader1",
                "組長一",
                "L001",
                "group_leader",
                "grpBio",
            )

            self.insert_user(
                conn,
                "leader2",
                "組長二",
                "L002",
                "group_leader",
                "grpMicro",
            )

            self.insert_user(
                conn,
                "admin1",
                "教學管理者",
                "A001",
                "education_admin",
                "grpBio",
            )

            self.insert_user(
                conn,
                "sys1",
                "系統管理者",
                "A002",
                "system_admin",
                "grpBio",
            )

        self.users = {
            "student1": {
                "username": "student1",
                "name": "學員一",
                "role": "student",
                "preferredGroup": "grpBio",
            },
            "student2": {
                "username": "student2",
                "name": "學員二",
                "role": "student",
                "preferredGroup": "grpBio",
            },
            "teacher1": {
                "username": "teacher1",
                "name": "教師一",
                "role": "clinical_teacher",
                "preferredGroup": "grpBio",
            },
            "teacher2": {
                "username": "teacher2",
                "name": "教師二",
                "role": "clinical_teacher",
                "preferredGroup": "grpBio",
            },
            "leader1": {
                "username": "leader1",
                "name": "組長一",
                "role": "group_leader",
                "preferredGroup": "grpBio",
            },
            "leader2": {
                "username": "leader2",
                "name": "組長二",
                "role": "group_leader",
                "preferredGroup": "grpMicro",
            },
            "admin1": {
                "username": "admin1",
                "name": "教學管理者",
                "role": "education_admin",
                "preferredGroup": "grpBio",
            },
            "sys1": {
                "username": "sys1",
                "name": "系統管理者",
                "role": "system_admin",
                "preferredGroup": "grpBio",
            },
        }

        self.actor = None

        self.app = create_app()
        self.app.config.update(
            TESTING=True
        )

        @self.app.before_request
        def bind_pgy_actor():
            g.pgy_user = self.actor

        self.client = (
            self.app.test_client()
        )

    def tearDown(self):
        if self.old_database_url is None:
            os.environ.pop(
                "DATABASE_URL",
                None,
            )
        else:
            os.environ[
                "DATABASE_URL"
            ] = self.old_database_url

        if self.old_sqlite is None:
            os.environ.pop(
                "TEACHER_SQLITE_PATH",
                None,
            )
        else:
            os.environ[
                "TEACHER_SQLITE_PATH"
            ] = self.old_sqlite

        self.db_path.unlink(
            missing_ok=True
        )

    @staticmethod
    def insert_user(
        conn,
        username,
        display_name,
        emp_id,
        role,
        group,
    ):
        execute(
            conn,
            """
            INSERT INTO user_accounts
            (
                username,
                display_name,
                emp_id,
                role,
                preferred_group,
                active
            )
            VALUES (?,?,?,?,?,1)
            """,
            (
                username,
                display_name,
                emp_id,
                role,
                group,
            ),
        )

    def as_user(self, username):
        self.actor = self.users[
            username
        ]

    def create_assignment(self):
        self.as_user("admin1")

        response = self.client.post(
            "/api/pgy/assignments",
            json={
                "learnerUsername":
                    "student1",
                "teacherUsername":
                    "teacher1",
                "group": "grpBio",
                "title":
                    "PGY HTTP integration",
            },
        )

        self.assertEqual(
            response.status_code,
            201,
            response.get_data(
                as_text=True
            ),
        )

        return response.get_json()[
            "assignment"
        ]["id"]

    def prepare_submitted(self):
        assignment_id = (
            self.create_assignment()
        )

        self.as_user("student1")

        updated = self.client.patch(
            f"/api/pgy/assignments/"
            f"{assignment_id}",
            json={
                "reflection":
                    "integration reflection"
            },
        )

        self.assertEqual(
            updated.status_code,
            200,
        )

        submitted = self.client.post(
            f"/api/pgy/assignments/"
            f"{assignment_id}/submit",
            json={},
        )

        self.assertEqual(
            submitted.status_code,
            200,
        )

        self.assertEqual(
            submitted.get_json()[
                "assignment"
            ]["status"],
            "submitted",
        )

        return assignment_id

    def test_full_http_workflow_and_audit(self):
        assignment_id = (
            self.prepare_submitted()
        )

        # Wrong teacher
        self.as_user("teacher2")

        denied = self.client.post(
            f"/api/pgy/assignments/"
            f"{assignment_id}/teacher-sign",
            json={"comment": "bad"},
        )

        self.assertEqual(
            denied.status_code,
            403,
        )

        # Correct teacher
        self.as_user("teacher1")

        signed = self.client.post(
            f"/api/pgy/assignments/"
            f"{assignment_id}/teacher-sign",
            json={"comment": "ok"},
        )

        self.assertEqual(
            signed.status_code,
            200,
        )

        self.assertEqual(
            signed.get_json()[
                "assignment"
            ]["status"],
            "teacher_signed",
        )

        duplicate = self.client.post(
            f"/api/pgy/assignments/"
            f"{assignment_id}/teacher-sign",
            json={"comment": "again"},
        )

        self.assertEqual(
            duplicate.status_code,
            409,
        )

        # Wrong leader
        self.as_user("leader2")

        denied_leader = (
            self.client.post(
                f"/api/pgy/assignments/"
                f"{assignment_id}/countersign",
                json={"comment": "bad"},
            )
        )

        self.assertEqual(
            denied_leader.status_code,
            403,
        )

        # Correct leader
        self.as_user("leader1")

        countersigned = (
            self.client.post(
                f"/api/pgy/assignments/"
                f"{assignment_id}/countersign",
                json={"comment": "ok"},
            )
        )

        self.assertEqual(
            countersigned.status_code,
            200,
        )

        self.assertEqual(
            countersigned.get_json()[
                "assignment"
            ]["status"],
            "group_countersigned",
        )

        duplicate_counter = (
            self.client.post(
                f"/api/pgy/assignments/"
                f"{assignment_id}/countersign",
                json={"comment": "again"},
            )
        )

        self.assertEqual(
            duplicate_counter.status_code,
            409,
        )

        # Finalize
        self.as_user("admin1")

        finalized = self.client.post(
            f"/api/pgy/assignments/"
            f"{assignment_id}/finalize",
            json={"comment": "done"},
        )

        self.assertEqual(
            finalized.status_code,
            200,
        )

        self.assertEqual(
            finalized.get_json()[
                "assignment"
            ]["status"],
            "finalized",
        )

        duplicate_final = (
            self.client.post(
                f"/api/pgy/assignments/"
                f"{assignment_id}/finalize",
                json={"comment": "again"},
            )
        )

        self.assertEqual(
            duplicate_final.status_code,
            409,
        )

        audit_response = self.client.get(
            "/api/pgy/audit",
            query_string={
                "assignmentId":
                    assignment_id
            },
        )

        self.assertEqual(
            audit_response.status_code,
            200,
        )

        audit = (
            audit_response.get_json()
        )

        expected = {
            "submit": (
                "assigned",
                "submitted",
                "student1",
                "student",
            ),
            "teacher_sign": (
                "submitted",
                "teacher_signed",
                "teacher1",
                "clinical_teacher",
            ),
            "group_countersign": (
                "teacher_signed",
                "group_countersigned",
                "leader1",
                "group_leader",
            ),
            "finalize": (
                "group_countersigned",
                "finalized",
                "admin1",
                "education_admin",
            ),
        }

        for (
            action,
            (
                from_status,
                to_status,
                username,
                role,
            ),
        ) in expected.items():
            rows = [
                row
                for row in audit
                if row["action"] == action
            ]

            self.assertEqual(
                len(rows),
                1,
                f"{action} should have "
                "exactly one audit row",
            )

            row = rows[0]

            self.assertEqual(
                row["fromStatus"],
                from_status,
            )
            self.assertEqual(
                row["toStatus"],
                to_status,
            )
            self.assertEqual(
                row["actorUsername"],
                username,
            )
            self.assertEqual(
                row["actorRole"],
                role,
            )

    def test_admin_roles_cannot_teacher_sign(self):
        for username in (
            "admin1",
            "sys1",
        ):
            assignment_id = (
                self.prepare_submitted()
            )

            self.as_user(username)

            response = (
                self.client.post(
                    f"/api/pgy/assignments/"
                    f"{assignment_id}/"
                    "teacher-sign",
                    json={
                        "comment":
                            "impersonation"
                    },
                )
            )

            self.assertEqual(
                response.status_code,
                403,
                username,
            )


if __name__ == "__main__":
    unittest.main()
