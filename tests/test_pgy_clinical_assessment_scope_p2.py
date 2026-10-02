import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from teacher_app.pgy import assessments


TEACHER = {
    "username": "teacher1",
    "name": "指派教師",
    "role": "clinical_teacher",
    "roles": ["clinical_teacher"],
    "preferredGroup": "grpBio",
}
TEACHER2 = {
    "username": "teacher2",
    "name": "同組未指派教師",
    "role": "clinical_teacher",
    "roles": ["clinical_teacher"],
    "preferredGroup": "grpBio",
}


def dops_payload(emp_id="S001", name="瀏覽器偽造姓名", group="grpBio"):
    return {
        "assessmentType": "dops",
        "group": group,
        "name": name,
        "empId": emp_id,
        "assessmentDate": "2026-10-02",
        "title": "DOPS",
        "comments": "完成觀察",
        "details": {
            "ratings": [
                {"item": item, "rating": 4, "note": ""}
                for item in assessments.PGY_ASSESSMENT_ITEMS["dops"]
            ]
        },
    }


class PgyClinicalAssessmentScopeP2Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE user_accounts(
                username TEXT PRIMARY KEY,
                display_name TEXT NOT NULL DEFAULT '',
                emp_id TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'student',
                roles_json TEXT NOT NULL DEFAULT '[]',
                preferred_group TEXT NOT NULL DEFAULT 'grpBio',
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE pgy_assignments(
                id TEXT PRIMARY KEY,
                learner_username TEXT NOT NULL,
                teacher_username TEXT NOT NULL,
                training_area TEXT NOT NULL DEFAULT 'pgy',
                group_key TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE pgy_assessments(
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                assessment_type TEXT NOT NULL,
                group_key TEXT NOT NULL DEFAULT 'grpBio',
                name TEXT NOT NULL,
                emp_id TEXT NOT NULL,
                evaluator_name TEXT NOT NULL DEFAULT '',
                evaluator_title TEXT NOT NULL DEFAULT '',
                assessment_date TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                details TEXT NOT NULL DEFAULT '{}',
                comments TEXT NOT NULL DEFAULT '',
                overall_score REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'completed'
            );
            """
        )
        self.conn.executemany(
            """
            INSERT INTO user_accounts(
                username,display_name,emp_id,role,roles_json,preferred_group,active
            ) VALUES (?,?,?,?,?,?,1)
            """,
            [
                ("student1", "正式學員甲", "S001", "student", '["student"]', "grpBio"),
                ("student2", "正式學員乙", "S002", "student", '["student"]', "grpBio"),
                ("student3", "血液學員", "S003", "student", '["student"]', "grpHema"),
            ],
        )
        self.conn.executemany(
            """
            INSERT INTO pgy_assignments(
                id,learner_username,teacher_username,training_area,group_key,status,updated_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            [
                ("a1", "student1", "teacher1", "pgy", "grpBio", "assigned", "2026-10-02T00:00:00+00:00"),
                ("a2", "student2", "teacher2", "pgy", "grpBio", "assigned", "2026-10-02T00:00:00+00:00"),
                ("a3", "student3", "teacher1", "pgy", "grpHema", "assigned", "2026-10-02T00:00:00+00:00"),
            ],
        )
        self.conn.commit()

        @contextmanager
        def tx():
            try:
                yield self.conn, "sqlite"
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

        @contextmanager
        def reader():
            yield self.conn, "sqlite"

        self.tx = tx
        self.reader = reader

    def tearDown(self):
        self.conn.close()

    def create(self, user, payload):
        with patch.object(assessments.common_db, "transaction", self.tx), patch.object(
            assessments.audit, "record_event"
        ) as audit:
            record_id = assessments.create_assessment(user, payload)
        return record_id, audit

    def list_for(self, user, **kwargs):
        with patch.object(assessments.common_db, "read_connection", self.reader):
            return assessments.list_assessments(user, **kwargs)

    def test_assigned_teacher_can_create_and_server_identity_replaces_browser_name(self):
        record_id, audit = self.create(TEACHER, dops_payload(name="假的名字"))
        row = self.conn.execute(
            "SELECT * FROM pgy_assessments WHERE id=?", (record_id,)
        ).fetchone()
        self.assertEqual(row["name"], "正式學員甲")
        self.assertEqual(row["emp_id"], "S001")
        self.assertEqual(row["evaluator_name"], "指派教師")
        self.assertEqual(row["evaluator_title"], "臨床教師")
        audit.assert_called_once()
        kwargs = audit.call_args.kwargs
        self.assertEqual(kwargs["action"], "pgy.assessment.create")
        self.assertEqual(kwargs["target_id"], record_id)
        self.assertEqual(kwargs["scope"]["learnerUsername"], "student1")
        self.assertEqual(kwargs["scope"]["assignmentId"], "a1")

    def test_same_group_but_unassigned_teacher_cannot_create(self):
        with self.assertRaises(assessments.AssessmentError) as caught:
            self.create(TEACHER2, dops_payload(emp_id="S001"))
        self.assertEqual(caught.exception.status, 403)
        self.assertIn("明確指派", str(caught.exception))
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM pgy_assessments").fetchone()[0],
            0,
        )

    def test_cross_group_target_cannot_be_selected_by_browser_payload(self):
        with self.assertRaises(assessments.AssessmentError) as caught:
            self.create(
                TEACHER,
                dops_payload(emp_id="S003", group="grpHema"),
            )
        self.assertEqual(caught.exception.status, 403)

    def test_finalized_or_cancelled_assignment_does_not_authorize_new_assessment(self):
        self.conn.execute("UPDATE pgy_assignments SET status='finalized' WHERE id='a1'")
        self.conn.commit()
        with self.assertRaises(assessments.AssessmentError) as caught:
            self.create(TEACHER, dops_payload())
        self.assertEqual(caught.exception.status, 403)

        self.conn.execute("UPDATE pgy_assignments SET status='cancelled' WHERE id='a1'")
        self.conn.commit()
        with self.assertRaises(assessments.AssessmentError) as caught2:
            self.create(TEACHER, dops_payload())
        self.assertEqual(caught2.exception.status, 403)

    def test_clinical_teacher_history_is_assignment_scoped_not_whole_group(self):
        self.conn.executemany(
            """
            INSERT INTO pgy_assessments(
                id,created_at,assessment_type,group_key,name,emp_id,evaluator_name,
                evaluator_title,assessment_date,title,details,comments,overall_score,status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                ("r1", "2026-10-02T00:00:00+00:00", "dops", "grpBio", "正式學員甲", "S001", "指派教師", "臨床教師", "2026-10-02", "DOPS", "{}", "", 4, "completed"),
                ("r2", "2026-10-02T00:01:00+00:00", "dops", "grpBio", "正式學員乙", "S002", "其他教師", "臨床教師", "2026-10-02", "DOPS", "{}", "", 4, "completed"),
            ],
        )
        self.conn.commit()
        rows = self.list_for(TEACHER)
        self.assertEqual([row["empId"] for row in rows], ["S001"])
        self.assertEqual(
            [row["empId"] for row in self.list_for(TEACHER, emp_id="S001")],
            ["S001"],
        )
        self.assertEqual(self.list_for(TEACHER, emp_id="S002"), [])

    def test_group_leader_own_group_and_education_admin_cross_group(self):
        self.conn.executemany(
            """
            INSERT INTO pgy_assessments(
                id,created_at,assessment_type,group_key,name,emp_id,evaluator_name,
                evaluator_title,assessment_date,title,details,comments,overall_score,status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                ("r1", "2026-10-02T00:00:00+00:00", "dops", "grpBio", "甲", "S001", "T", "臨床教師", "2026-10-02", "DOPS", "{}", "", 4, "completed"),
                ("r3", "2026-10-02T00:02:00+00:00", "dops", "grpHema", "丙", "S003", "T", "臨床教師", "2026-10-02", "DOPS", "{}", "", 4, "completed"),
            ],
        )
        self.conn.commit()
        leader = {
            "username": "leader1",
            "role": "group_leader",
            "roles": ["group_leader"],
            "preferredGroup": "grpBio",
        }
        edu = {
            "username": "edu1",
            "role": "education_admin",
            "roles": ["education_admin"],
            "preferredGroup": "grpBio",
        }
        self.assertEqual([row["empId"] for row in self.list_for(leader)], ["S001"])
        self.assertEqual(
            {row["empId"] for row in self.list_for(edu)},
            {"S001", "S003"},
        )

    def test_standalone_system_admin_cannot_read_clinical_assessments(self):
        system = {
            "username": "root",
            "role": "system_admin",
            "roles": ["system_admin"],
            "preferredGroup": "grpBio",
        }
        with self.assertRaises(assessments.AssessmentError) as caught:
            self.list_for(system)
        self.assertEqual(caught.exception.status, 403)


if __name__ == "__main__":
    unittest.main()
