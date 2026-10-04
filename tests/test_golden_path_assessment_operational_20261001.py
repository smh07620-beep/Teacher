import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from teacher_app.exams import records
from teacher_app.exams import repository as repo
from teacher_app.exams import service
from tests.exam_support import ExamBase


class AssessmentGoldenPathOperationalTests(unittest.TestCase):
    """GP-04: learner submission must become a scoped, server-attributed reviewed result."""

    def setUp(self):
        self.base = ExamBase()
        repo.init_schema(self.base)
        conn, _ = self.base._db_conn()
        try:
            conn.execute("ALTER TABLE exam_records ADD COLUMN reviewed_at TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE exam_records ADD COLUMN reviewer_name TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE exam_records ADD COLUMN review_comment TEXT NOT NULL DEFAULT ''")
            conn.execute("""CREATE TABLE user_accounts (
                username TEXT PRIMARY KEY, emp_id TEXT NOT NULL, preferred_group TEXT NOT NULL DEFAULT 'grpBio'
            )""")
            conn.execute("""CREATE TABLE pgy_assignments (
                id TEXT PRIMARY KEY, learner_username TEXT NOT NULL, teacher_username TEXT NOT NULL,
                group_key TEXT NOT NULL DEFAULT 'grpBio', training_area TEXT NOT NULL DEFAULT 'pgy',
                status TEXT NOT NULL DEFAULT 'assigned'
            )""")
            # GP-04 exercises the production submit path, including the
            # server-authoritative deadline guard introduced by migration 0093.
            # Keep this focused fixture schema-aligned instead of weakening
            # teacher_app.exams.windows when a migration is missing.
            conn.execute("""CREATE TABLE exam_windows (
                quiz_category_id TEXT PRIMARY KEY, opens_at TEXT NOT NULL DEFAULT '',
                closes_at TEXT NOT NULL DEFAULT '', reminder_enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT '', updated_by TEXT NOT NULL DEFAULT ''
            )""")
            conn.execute(
                "INSERT INTO user_accounts(username,emp_id,preferred_group) VALUES (?,?,?)",
                ("student1", "S001", "grpBio"),
            )
            conn.execute(
                "INSERT INTO pgy_assignments(id,learner_username,teacher_username,group_key,status) VALUES (?,?,?,?,?)",
                ("assign1", "student1", "teacher1", "grpBio", "assigned"),
            )
        finally:
            conn.close()

        self.base.category.update({
            "reviewerName": "考卷設定教師",
            "reviewerTitle": "醫檢師",
        })
        self.category_patch = patch.object(
            service.assessment_repository,
            "get_category_full",
            side_effect=self.base.get_quiz_category,
        )
        self.questions_patch = patch.object(
            service.assessment_repository,
            "list_questions",
            side_effect=lambda category_id, include_inactive=False: [
                dict(question)
                for question in self.base.list_quiz_questions(category_id)
                if include_inactive or question.get("active", True)
            ],
        )
        self.window_patch = patch.object(service, "assert_exam_open", return_value=None)
        # submit_attempt uses exams.windows.assert_exam_not_closed directly;
        # route its read connection to this test's SQLite database too.
        self.window_db_patch = patch.object(
            service.assert_exam_not_closed.__globals__["common_db"],
            "read_connection",
            side_effect=lambda: self._read_connection(),
        )
        self.shuffle_patch = patch.object(service.random, "shuffle", side_effect=lambda items: None)
        self.transaction_patch = patch.object(
            records.common_db,
            "transaction",
            side_effect=lambda: self._transaction(),
        )
        for active_patch in (
            self.category_patch,
            self.questions_patch,
            self.window_patch,
            self.window_db_patch,
            self.shuffle_patch,
            self.transaction_patch,
        ):
            active_patch.start()
            self.addCleanup(active_patch.stop)
        self.audit_patch = patch.object(records.audit, "record_event", return_value={"id": "audit1"})
        self.audit_mock = self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)

    def tearDown(self):
        self.base.close()

    @contextmanager
    def _read_connection(self):
        conn, kind = self.base._db_conn()
        try:
            yield conn, kind
        finally:
            conn.close()

    @contextmanager
    def _transaction(self):
        conn, kind = self.base._db_conn()
        try:
            conn.execute("BEGIN")
            yield conn, kind
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _submit_essay(self):
        started = service.start_attempt(
            self.base,
            self.base.user,
            {"quizCategoryId": "quiz1"},
        )
        submitted = service.submit_attempt(
            self.base,
            self.base.user,
            started["attemptId"],
            {
                "answers": [1, "申論作答"],
                "evaluatorName": "Browser Fake Evaluator",
                "evaluatorTitle": "Browser Fake Title",
                "examineeRole": "student",
            },
        )
        return started, submitted

    @staticmethod
    def _review_payload():
        return {
            "essayScores": {"1": 100},
            "essayComments": {"1": "內容完整"},
            "reviewComment": "完成人工批改",
            "reviewerName": "Browser Fake Reviewer",
            "groupKey": "grpHema",
            "empId": "SPOOFED",
        }

    def test_submit_review_and_result_use_server_authoritative_identity_and_assignment(self):
        started, submitted = self._submit_essay()
        self.assertEqual(started["evaluatorName"], "考卷設定教師")
        self.assertEqual(started["evaluatorTitle"], "醫檢師")
        self.assertEqual(submitted["status"], "待人工批改")

        reviewer_user = {
            "username": "teacher1",
            "name": "王老師",
            "title": "資深醫檢師",
            "role": "clinical_teacher",
            "preferredGroup": "grpHema",
        }
        reviewed = records.review_record(
            submitted["recordId"],
            self._review_payload(),
            reviewer_user=reviewer_user,
        )
        self.assertTrue(reviewed["ok"])
        self.assertEqual(reviewed["score"], 100)
        self.assertEqual(reviewed["status"], "合格")
        self.assertEqual(reviewed["reviewerName"], "王老師")
        self.assertEqual(reviewed["reviewerTitle"], "資深醫檢師")

        conn, _ = self.base._db_conn()
        try:
            row = conn.execute(
                "SELECT review_status,reviewer_name,evaluator_name,evaluator_title,answers_detail "
                "FROM exam_records WHERE id=?",
                (submitted["recordId"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row["review_status"], "completed")
        self.assertEqual(row["reviewer_name"], "王老師")
        self.assertEqual(row["evaluator_name"], "考卷設定教師")
        self.assertEqual(row["evaluator_title"], "醫檢師")
        answers = json.loads(row["answers_detail"])
        essay = next(answer for answer in answers if answer.get("questionType") == "essay")
        self.assertEqual(essay["reviewerName"], "王老師")
        self.assertEqual(essay["reviewerTitle"], "資深醫檢師")
        self.assertNotEqual(essay["reviewerName"], "Browser Fake Reviewer")
        self.audit_mock.assert_called_once()
        audit_call = self.audit_mock.call_args.kwargs
        self.assertEqual(audit_call["action"], "exam.record.review")
        self.assertEqual(audit_call["scope"]["kind"], "assigned_student")
        self.assertEqual(audit_call["scope"]["empId"], "S001")

    def test_unassigned_clinical_teacher_cannot_review_or_spoof_scope(self):
        _started, submitted = self._submit_essay()
        reviewer_user = {
            "username": "teacher2",
            "name": "未指派教師",
            "role": "clinical_teacher",
            "preferredGroup": "grpBio",
        }
        with self.assertRaises(records.RecordError) as denied:
            records.review_record(
                submitted["recordId"],
                self._review_payload(),
                reviewer_user=reviewer_user,
            )
        self.assertEqual(denied.exception.status, 403)
        self.assertIn("未指派", str(denied.exception))

    def test_group_leader_can_review_own_group_but_not_cross_group(self):
        _started, submitted = self._submit_essay()
        leader = {
            "username": "leader1",
            "name": "生化組長",
            "role": "group_leader",
            "preferredGroup": "grpBio",
        }
        reviewed = records.review_record(
            submitted["recordId"],
            self._review_payload(),
            reviewer_user=leader,
        )
        self.assertTrue(reviewed["ok"])

        # A second pending record in grpBio remains protected from another group's leader.
        _started2, submitted2 = self._submit_essay()
        other_leader = {
            "username": "leader2",
            "name": "血液組長",
            "role": "group_leader",
            "preferredGroup": "grpHema",
        }
        with self.assertRaises(records.RecordError) as denied:
            records.review_record(
                submitted2["recordId"],
                self._review_payload(),
                reviewer_user=other_leader,
            )
        self.assertEqual(denied.exception.status, 403)

    def test_manual_review_requires_authenticated_reviewer_identity(self):
        _started, submitted = self._submit_essay()
        with self.assertRaises(records.RecordError) as denied:
            records.review_record(
                submitted["recordId"],
                {"essayScores": {"1": 100}, "reviewerName": "Browser Fake Reviewer"},
                reviewer_user=None,
            )
        self.assertEqual(denied.exception.status, 401)


if __name__ == "__main__":
    unittest.main()
