import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from teacher_app.common.db import (
    execute,
    fetch_one,
    transaction,
)
from teacher_app.common.errors import (
    ApiError,
)
from teacher_app.pgy import (
    repository as repo,
)
from teacher_app.pgy import signing


class PgySigning66Tests(
    unittest.TestCase
):
    def setUp(self):
        handle, path = (
            tempfile.mkstemp(
                suffix=".db"
            )
        )
        os.close(handle)

        self.db_path = Path(
            path
        )

        self.previous_db_url = (
            os.environ.pop(
                "DATABASE_URL",
                None,
            )
        )

        self.previous_sqlite = (
            os.environ.get(
                "TEACHER_SQLITE_PATH"
            )
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

            signing.ensure_schema_connection(
                conn,
                kind,
            )

            self._insert_user(
                conn,
                "student1",
                "學員",
                "S001",
                "student",
                "grpBio",
            )

            self._insert_user(
                conn,
                "teacher1",
                "教師一",
                "T001",
                "clinical_teacher",
                "grpBio",
            )

            self._insert_user(
                conn,
                "leader1",
                "組長一",
                "L001",
                "group_leader",
                "grpBio",
            )

            self._insert_user(
                conn,
                "leader2",
                "組長二",
                "L002",
                "group_leader",
                "grpMicro",
            )

        self.teacher = {
            "username":
                "teacher1",
            "name":
                "教師一",
            "role":
                "clinical_teacher",
            "roles":
                [
                    "clinical_teacher",
                ],
            "preferredGroup":
                "grpBio",
        }

        self.leader = {
            "username":
                "leader1",
            "name":
                "組長一",
            "role":
                "group_leader",
            "roles":
                [
                    "group_leader",
                ],
            "preferredGroup":
                "grpBio",
        }

        self.wrong_leader = {
            "username":
                "leader2",
            "name":
                "組長二",
            "role":
                "group_leader",
            "roles":
                [
                    "group_leader",
                ],
            "preferredGroup":
                "grpMicro",
        }

        self.admin = {
            "username":
                "admin1",
            "name":
                "管理者",
            "role":
                "education_admin",
            "roles":
                [
                    "education_admin",
                ],
            "preferredGroup":
                "grpBio",
        }

        self.multi = {
            "username":
                "teacher1",
            "name":
                "教師兼組長",
            "role":
                "clinical_teacher",
            "roles":
                [
                    "clinical_teacher",
                    "group_leader",
                ],
            "preferredGroup":
                "grpBio",
        }

    def tearDown(self):
        if (
            self.previous_db_url
            is not None
        ):
            os.environ[
                "DATABASE_URL"
            ] = self.previous_db_url
        else:
            os.environ.pop(
                "DATABASE_URL",
                None,
            )

        if (
            self.previous_sqlite
            is None
        ):
            os.environ.pop(
                "TEACHER_SQLITE_PATH",
                None,
            )
        else:
            os.environ[
                "TEACHER_SQLITE_PATH"
            ] = self.previous_sqlite

        self.db_path.unlink(
            missing_ok=True
        )

    @staticmethod
    def _insert_user(
        conn,
        username,
        name,
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
                name,
                emp_id,
                role,
                group,
            ),
        )

    def _seed(
        self,
        mode,
        status="submitted",
    ):
        assignment_id = (
            uuid.uuid4().hex
        )

        with transaction() as (
            conn,
            kind,
        ):
            repo.create_assignment(
                conn,
                kind,
                assignment_id=
                    assignment_id,
                learner_username=
                    "student1",
                teacher_username=
                    "teacher1",
                group_key=
                    "grpBio",
                course_id="",
                title="PGY",
                instructions="",
                due_at="",
                created_by="admin1",
                created_at=
                    "2026-09-09T00:00:00+00:00",
            )

            execute(
                conn,
                """
                UPDATE pgy_assignments
                SET status=?,
                    sign_mode=?
                WHERE id=?
                """,
                (
                    status,
                    mode,
                    assignment_id,
                ),
            )

        return assignment_id

    def _row(
        self,
        assignment_id,
    ):
        with transaction() as (
            conn,
            _kind,
        ):
            return fetch_one(
                conn,
                """
                SELECT *
                FROM pgy_assignments
                WHERE id=?
                """,
                (
                    assignment_id,
                ),
            )

    def _audit_count(
        self,
        assignment_id,
    ):
        with transaction() as (
            conn,
            _kind,
        ):
            return int(
                fetch_one(
                    conn,
                    """
                    SELECT COUNT(*) AS n
                    FROM pgy_assignment_audit
                    WHERE assignment_id=?
                    """,
                    (
                        assignment_id,
                    ),
                )["n"]
            )

    def test_existing_rows_default_to_legacy(self):
        assignment_id = (
            self._seed(
                "legacy"
            )
        )

        row = self._row(
            assignment_id
        )

        self.assertEqual(
            row[
                "sign_mode"
            ],
            "legacy",
        )

    def test_single_assigned_teacher_signs_once_and_finishes(self):
        assignment_id = (
            self._seed(
                "single"
            )
        )

        result = (
            signing.sign_assignment(
                self.teacher,
                assignment_id,
                {
                    "comment":
                        "確認"
                },
            )
        )

        self.assertEqual(
            result["status"],
            "finalized",
        )

        self.assertEqual(
            result[
                "firstSignature"
            ][
                "role"
            ],
            "clinical_teacher",
        )

        self.assertEqual(
            self._audit_count(
                assignment_id
            ),
            1,
        )

    def test_single_group_leader_can_sign_and_finish(self):
        assignment_id = (
            self._seed(
                "single"
            )
        )

        result = (
            signing.sign_assignment(
                self.leader,
                assignment_id,
                {},
            )
        )

        self.assertEqual(
            result["status"],
            "finalized",
        )

        self.assertEqual(
            result[
                "firstSignature"
            ][
                "role"
            ],
            "group_leader",
        )

    def test_admin_without_signer_role_cannot_sign(self):
        assignment_id = (
            self._seed(
                "single"
            )
        )

        with self.assertRaises(
            ApiError
        ) as denied:
            signing.sign_assignment(
                self.admin,
                assignment_id,
                {},
            )

        self.assertEqual(
            denied.exception.status,
            403,
        )

        self.assertEqual(
            self._row(
                assignment_id
            )[
                "status"
            ],
            "submitted",
        )

    def test_dual_requires_second_different_account(self):
        assignment_id = (
            self._seed(
                "dual"
            )
        )

        first = (
            signing.sign_assignment(
                self.multi,
                assignment_id,
                {},
            )
        )

        self.assertEqual(
            first["status"],
            "teacher_signed",
        )

        with self.assertRaises(
            ApiError
        ) as denied:
            signing.countersign_assignment(
                self.multi,
                assignment_id,
                {},
            )

        self.assertEqual(
            denied.exception.code,
            "SAME_SIGNER",
        )

        self.assertEqual(
            self._row(
                assignment_id
            )[
                "status"
            ],
            "teacher_signed",
        )

        self.assertEqual(
            self._audit_count(
                assignment_id
            ),
            1,
        )

    def test_dual_second_signer_finishes(self):
        assignment_id = (
            self._seed(
                "dual"
            )
        )

        signing.sign_assignment(
            self.teacher,
            assignment_id,
            {},
        )

        result = (
            signing.countersign_assignment(
                self.leader,
                assignment_id,
                {
                    "comment":
                        "覆核完成"
                },
            )
        )

        self.assertEqual(
            result["status"],
            "finalized",
        )

        self.assertEqual(
            result[
                "firstSignature"
            ][
                "username"
            ],
            "teacher1",
        )

        self.assertEqual(
            result[
                "secondSignature"
            ][
                "username"
            ],
            "leader1",
        )

        self.assertEqual(
            self._audit_count(
                assignment_id
            ),
            2,
        )

    def test_wrong_group_leader_cannot_sign(self):
        assignment_id = (
            self._seed(
                "single"
            )
        )

        with self.assertRaises(
            ApiError
        ) as denied:
            signing.sign_assignment(
                self.wrong_leader,
                assignment_id,
                {},
            )

        self.assertEqual(
            denied.exception.status,
            403,
        )

    def test_audit_failure_rolls_back_primary_sign(self):
        assignment_id = (
            self._seed(
                "single"
            )
        )

        with patch.object(
            repo,
            "write_audit",
            side_effect=
                RuntimeError(
                    "audit down"
                ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                signing.sign_assignment(
                    self.teacher,
                    assignment_id,
                    {},
                )

        row = self._row(
            assignment_id
        )

        self.assertEqual(
            row[
                "status"
            ],
            "submitted",
        )

        self.assertEqual(
            repo.json_load(
                row[
                    "first_signature"
                ],
                {},
            ),
            {},
        )

        self.assertEqual(
            self._audit_count(
                assignment_id
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
