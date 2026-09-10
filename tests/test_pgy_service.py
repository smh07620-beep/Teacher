import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from teacher_app.common.db import execute, fetch_one, transaction
from teacher_app.common.errors import ApiError
from teacher_app.pgy import repository as repo
from teacher_app.pgy import service
from pgy_atomic import _legacy_error_body


class PgyServiceTests(unittest.TestCase):
    def setUp(self):
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db_path = Path(path)
        self.previous_db_url = os.environ.pop("DATABASE_URL", None)
        self.previous_sqlite_path = os.environ.get("TEACHER_SQLITE_PATH")
        os.environ["TEACHER_SQLITE_PATH"] = str(self.db_path)
        with transaction() as (conn, kind):
            repo.init_schema(conn, kind)
            self._insert_user(conn, "student1", "學員一", "S001", "student", "grpBio")
            self._insert_user(conn, "teacher1", "教師一", "T001", "clinical_teacher", "grpBio")
            self._insert_user(conn, "teacher2", "教師二", "T002", "clinical_teacher", "grpBio")
            self._insert_user(conn, "leader1", "組長一", "L001", "group_leader", "grpBio")
            self._insert_user(conn, "leader2", "組長二", "L002", "group_leader", "grpMicro")
            self._insert_user(conn, "admin1", "教學管理者", "A001", "education_admin", "grpBio")
            self._insert_user(conn, "sys1", "系統管理者", "A002", "system_admin", "grpBio")

        self.student = {"username": "student1", "name": "學員一", "role": "student", "preferredGroup": "grpBio"}
        self.teacher1 = {"username": "teacher1", "name": "教師一", "role": "clinical_teacher", "preferredGroup": "grpBio"}
        self.teacher2 = {"username": "teacher2", "name": "教師二", "role": "clinical_teacher", "preferredGroup": "grpBio"}
        self.leader1 = {"username": "leader1", "name": "組長一", "role": "group_leader", "preferredGroup": "grpBio"}
        self.leader2 = {"username": "leader2", "name": "組長二", "role": "group_leader", "preferredGroup": "grpMicro"}
        self.admin = {"username": "admin1", "name": "教學管理者", "role": "education_admin", "preferredGroup": "grpBio"}
        self.system_admin = {"username": "sys1", "name": "系統管理者", "role": "system_admin", "preferredGroup": "grpBio"}

    def tearDown(self):
        if self.previous_db_url is not None:
            os.environ["DATABASE_URL"] = self.previous_db_url
        else:
            os.environ.pop("DATABASE_URL", None)
        if self.previous_sqlite_path is None:
            os.environ.pop("TEACHER_SQLITE_PATH", None)
        else:
            os.environ["TEACHER_SQLITE_PATH"] = self.previous_sqlite_path
        self.db_path.unlink(missing_ok=True)

    @staticmethod
    def _insert_user(conn, username, display_name, emp_id, role, group):
        execute(
            conn,
            "INSERT INTO user_accounts (username,display_name,emp_id,role,preferred_group,active) VALUES (?,?,?,?,?,1)",
            (username, display_name, emp_id, role, group),
        )

    def _seed_assignment(self, status: str, *, group="grpBio", teacher="teacher1") -> str:
        assignment_id = uuid.uuid4().hex
        with transaction() as (conn, kind):
            repo.create_assignment(
                conn,
                kind,
                assignment_id=assignment_id,
                learner_username="student1",
                teacher_username=teacher,
                group_key=group,
                course_id="",
                title="PGY test",
                instructions="",
                due_at="",
                created_by="admin1",
                created_at="2026-09-09T00:00:00+00:00",
            )
            if status != "assigned":
                execute(conn, "UPDATE pgy_assignments SET status=? WHERE id=?", (status, assignment_id))
        return assignment_id

    def _status(self, assignment_id: str) -> str:
        with transaction() as (conn, _kind):
            return fetch_one(conn, "SELECT status FROM pgy_assignments WHERE id=?", (assignment_id,))["status"]

    def _audit_count(self, assignment_id: str) -> int:
        with transaction() as (conn, _kind):
            return int(fetch_one(conn, "SELECT COUNT(*) AS n FROM pgy_assignment_audit WHERE assignment_id=?", (assignment_id,))["n"])

    def test_teacher_double_sign_only_first_succeeds(self):
        assignment_id = self._seed_assignment("submitted")
        first = service.teacher_sign_assignment(self.teacher1, assignment_id, {"comment": "ok"})
        self.assertEqual(first["status"], "teacher_signed")
        with self.assertRaises(ApiError) as second:
            service.teacher_sign_assignment(self.teacher1, assignment_id, {"comment": "again"})
        self.assertEqual(second.exception.status, 409)
        self.assertEqual(self._audit_count(assignment_id), 1)

    def test_group_double_countersign_only_first_succeeds(self):
        assignment_id = self._seed_assignment("teacher_signed")
        first = service.group_countersign_assignment(self.leader1, assignment_id, {"comment": "ok"})
        self.assertEqual(first["status"], "group_countersigned")
        with self.assertRaises(ApiError) as second:
            service.group_countersign_assignment(self.leader1, assignment_id, {"comment": "again"})
        self.assertEqual(second.exception.status, 409)
        self.assertEqual(self._audit_count(assignment_id), 1)

    def test_finalize_double_submit_only_first_succeeds(self):
        assignment_id = self._seed_assignment("group_countersigned")
        first = service.finalize_assignment(self.admin, assignment_id, {"comment": "done"})
        self.assertEqual(first["status"], "finalized")
        with self.assertRaises(ApiError) as second:
            service.finalize_assignment(self.admin, assignment_id, {"comment": "again"})
        self.assertEqual(second.exception.status, 409)
        self.assertEqual(self._audit_count(assignment_id), 1)

    def test_wrong_teacher_cannot_sign(self):
        assignment_id = self._seed_assignment("submitted")
        with self.assertRaises(ApiError) as denied:
            service.teacher_sign_assignment(self.teacher2, assignment_id, {})
        self.assertEqual(denied.exception.status, 403)
        self.assertEqual(self._status(assignment_id), "submitted")
        self.assertEqual(self._audit_count(assignment_id), 0)

    def test_wrong_group_leader_cannot_countersign(self):
        assignment_id = self._seed_assignment("teacher_signed")
        with self.assertRaises(ApiError) as denied:
            service.group_countersign_assignment(self.leader2, assignment_id, {})
        self.assertEqual(denied.exception.status, 403)
        self.assertEqual(self._status(assignment_id), "teacher_signed")
        self.assertEqual(self._audit_count(assignment_id), 0)

    def test_admin_roles_cannot_impersonate_teacher_signature(self):
        for actor in (self.admin, self.system_admin):
            assignment_id = self._seed_assignment("submitted")
            with self.assertRaises(ApiError) as denied:
                service.teacher_sign_assignment(actor, assignment_id, {})
            self.assertEqual(denied.exception.status, 403)
            self.assertEqual(self._status(assignment_id), "submitted")

    def test_audit_failure_rolls_back_status_change(self):
        assignment_id = self._seed_assignment("submitted")
        with patch.object(repo, "write_audit", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                service.teacher_sign_assignment(self.teacher1, assignment_id, {})
        self.assertEqual(self._status(assignment_id), "submitted")
        self.assertEqual(self._audit_count(assignment_id), 0)

    def test_legacy_error_contract_remains_plain_error_string(self):
        body = _legacy_error_body(ApiError("TRANSITION_CONFLICT", "狀態衝突", status=409))
        self.assertEqual(body, {"error": "狀態衝突"})
        login = _legacy_error_body(ApiError("LOGIN_REQUIRED", "請先登入", status=401, extra={"loginRequired": True}))
        self.assertEqual(login, {"error": "請先登入", "loginRequired": True})


if __name__ == "__main__":
    unittest.main()
