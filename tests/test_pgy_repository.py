import os
import tempfile
import unittest
from pathlib import Path

from teacher_app.common.db import fetch_one, transaction
from teacher_app.pgy import repository as repo


class PgyRepositoryTests(unittest.TestCase):
    def setUp(self):
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db_path = Path(path)
        self.previous_db_url = os.environ.pop("DATABASE_URL", None)
        self.previous_sqlite_path = os.environ.get("TEACHER_SQLITE_PATH")
        os.environ["TEACHER_SQLITE_PATH"] = str(self.db_path)
        with transaction() as (conn, kind):
            repo.init_schema(conn, kind)

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

    def _seed_assignment(self, assignment_id="a1"):
        with transaction() as (conn, kind):
            repo.create_assignment(
                conn,
                kind,
                assignment_id=assignment_id,
                learner_username="student1",
                teacher_username="teacher1",
                group_key="grpBio",
                course_id="",
                title="PGY",
                instructions="",
                due_at="",
                created_by="admin1",
                created_at="2026-09-09T00:00:00+00:00",
            )

    def test_conditional_transition_allows_only_one_update(self):
        self._seed_assignment()
        with transaction() as (conn, kind):
            repo.transition_status(conn, kind, "a1", "assigned", "submitted", {"updated_at": "t1"})

        with self.assertRaises(repo.TransitionConflict):
            with transaction() as (conn, kind):
                repo.transition_status(conn, kind, "a1", "assigned", "submitted", {"updated_at": "t2"})

        with transaction() as (conn, _kind):
            row = fetch_one(conn, "SELECT status,updated_at FROM pgy_assignments WHERE id=?", ("a1",))
            self.assertEqual(row["status"], "submitted")
            self.assertEqual(row["updated_at"], "t1")

    def test_audit_round_trip_keeps_transition_fields(self):
        self._seed_assignment()
        with transaction() as (conn, kind):
            repo.write_audit(
                conn,
                kind,
                assignment_id="a1",
                action="submit",
                from_status="assigned",
                to_status="submitted",
                actor_username="student1",
                actor_role="student",
                detail={"source": "test"},
            )
        with transaction() as (conn, kind):
            rows = repo.list_audit(conn, kind, assignment_id="a1")
        self.assertEqual(len(rows), 1)
        item = repo.audit_dict(rows[0])
        self.assertEqual(item["assignmentId"], "a1")
        self.assertEqual(item["action"], "submit")
        self.assertEqual(item["fromStatus"], "assigned")
        self.assertEqual(item["toStatus"], "submitted")
        self.assertEqual(item["actorUsername"], "student1")
        self.assertEqual(item["actorRole"], "student")
        self.assertEqual(item["detail"], {"source": "test"})

    def test_transaction_rolls_back_transition_when_later_step_fails(self):
        self._seed_assignment()
        with self.assertRaises(RuntimeError):
            with transaction() as (conn, kind):
                repo.transition_status(conn, kind, "a1", "assigned", "submitted", {"updated_at": "t1"})
                raise RuntimeError("simulated audit failure")
        with transaction() as (conn, _kind):
            row = fetch_one(conn, "SELECT status FROM pgy_assignments WHERE id=?", ("a1",))
        self.assertEqual(row["status"], "assigned")


if __name__ == "__main__":
    unittest.main()
