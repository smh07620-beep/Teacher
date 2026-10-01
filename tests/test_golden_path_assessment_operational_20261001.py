import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from teacher_app.common import audit
from teacher_app.common import db as common_db
from teacher_app.exams import record_routes, records, repository as exam_repository, schema as exam_schema, service as exam_service
from teacher_app.learning import progress_service
from tests.exam_support import ExamBase


class AssessmentGoldenPathOperationalTests(unittest.TestCase):
    """GP-04: learner submission -> scoped teacher review -> learner-visible result."""

    def setUp(self):
        self.base = ExamBase()
        self.addCleanup(self.base.close)
        self.base.user.update({
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        })
        self.base.category.update({
            "reviewerName": "出題階段審核者",
            "reviewerTitle": "原始快照職稱",
        })
        exam_repository.init_schema(self.base)
        conn, kind = self.base._db_conn()
        try:
            exam_schema.init_schema(conn, kind)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS material_progress ("
                "emp_id TEXT NOT NULL,name TEXT NOT NULL,material_id TEXT NOT NULL,"
                "completed_at TEXT NOT NULL,PRIMARY KEY(emp_id,material_id))"
            )
        finally:
            conn.close()

        self.db_patch = patch.object(common_db, "get_connection", self.base._db_conn)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

        self.category_patch = patch.object(
            exam_service.assessment_repository,
            "get_category_full",
            side_effect=self.base.get_quiz_category,
        )
        self.questions_patch = patch.object(
            exam_service.assessment_repository,
            "list_questions",
            side_effect=lambda category_id, include_inactive=False: [
                dict(question)
                for question in self.base.list_quiz_questions(category_id)
                if include_inactive or question.get("active", True)
            ],
        )
        self.category_patch.start()
        self.questions_patch.start()
        self.addCleanup(self.category_patch.stop)
        self.addCleanup(self.questions_patch.stop)

        self.actor = dict(self.base.user)
        self.owner = SimpleNamespace(app=self.base.app)
        self.owner._current_user = lambda: self.actor
        record_routes.register_record_routes(self.owner)
        self.client = self.base.app.test_client()

    def test_gp04_submission_scoped_review_and_final_result_use_server_identity(self):
        started = exam_service.start_attempt(
            self.base,
            self.base.user,
            {"quizCategoryId": "quiz1"},
        )
        self.assertEqual(started["evaluatorName"], "出題階段審核者")
        self.assertEqual(started["evaluatorTitle"], "原始快照職稱")

        submitted = exam_service.submit_attempt(
            self.base,
            self.base.user,
            started["attemptId"],
            {
                "answers": [1, "申論作答"],
                "evaluatorName": "Browser Fake Evaluator",
                "evaluatorTitle": "Browser Fake Title",
                "score": 100,
                "status": "合格",
            },
        )
        record_id = submitted["recordId"]
        pending = records.get_record(record_id)
        self.assertIsNotNone(pending)
        self.assertEqual(pending["reviewStatus"], "pending")
        self.assertEqual(pending["status"], "待人工批改")
        self.assertEqual(pending["empId"], "S001")
        self.assertEqual(pending["groupKey"], "grpBio")
        self.assertEqual(pending["trainingArea"], "internal")
        self.assertNotEqual(pending["evaluatorName"], "Browser Fake Evaluator")

        # A teacher with valid exam.manage permission but the wrong group must
        # not be able to review this learner's record.
        self.actor = {
            "username": "teacher.micro",
            "name": "錯組教師",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredArea": "internal",
            "preferredGroup": "grpMicro",
            "professionalTitle": "醫檢師",
        }
        denied = self.client.patch(
            f"/api/records/{record_id}/review",
            json={
                "essayScores": {"1": 100},
                "reviewerName": "Browser Fake",
                "reviewerTitle": "Browser Fake",
            },
        )
        self.assertEqual(denied.status_code, 403, denied.get_data(as_text=True))
        self.assertEqual(records.get_record(record_id)["reviewStatus"], "pending")

        # The correct teaching-scope actor reviews it. Browser identity fields
        # deliberately lie; the route must ignore them and use session identity.
        self.actor = {
            "username": "teacher.bio",
            "name": "王老師",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
            "professionalTitle": "資深醫檢師",
        }
        with patch.object(audit, "record_event") as audit_event:
            reviewed = self.client.patch(
                f"/api/records/{record_id}/review",
                json={
                    "essayScores": {"1": 100},
                    "essayComments": {"1": "內容完整"},
                    "reviewComment": "完成教師審核",
                    "reviewerName": "Browser Fake",
                    "reviewerTitle": "Browser Fake",
                },
            )
        self.assertEqual(reviewed.status_code, 200, reviewed.get_data(as_text=True))
        body = reviewed.get_json()
        self.assertEqual(body["reviewerName"], "王老師")
        self.assertEqual(body["reviewerTitle"], "資深醫檢師")
        self.assertNotEqual(body["reviewerName"], "Browser Fake")

        final = records.get_record(record_id)
        self.assertEqual(final["reviewStatus"], "completed")
        self.assertEqual(final["reviewerName"], "王老師")
        self.assertEqual(final["evaluatorName"], "王老師")
        self.assertEqual(final["evaluatorTitle"], "資深醫檢師")
        self.assertEqual(final["reviewComment"], "完成教師審核")
        essay = next(item for item in final["answersDetail"] if item.get("questionType") == "essay")
        self.assertEqual(essay["reviewerName"], "王老師")
        self.assertEqual(essay["reviewerTitle"], "資深醫檢師")
        self.assertEqual(essay["reviewScore"], 100.0)

        audit_event.assert_called_once()
        audit_kwargs = audit_event.call_args.kwargs
        self.assertEqual(audit_kwargs["action"], "exam.record.review")
        self.assertEqual(audit_kwargs["target_id"], record_id)
        self.assertTrue(audit_kwargs["detail"]["reviewerDerivedFromSession"])

        # Learner-facing projection must now expose the reviewed record to the
        # same learner and scope; this is the final product outcome GP-04 guards.
        self.actor = dict(self.base.user)
        course = {
            "id": "course1",
            "title": "Golden Path 考核課程",
            "area": "internal",
            "group": "grpBio",
            "completionPolicy": {"examMode": "any"},
        }
        category = {
            "id": "quiz1",
            "title": "血液學測驗",
            "courseId": "course1",
            "area": "internal",
            "group": "grpBio",
            "active": True,
        }
        with patch.object(progress_service.course_repository, "list_courses", return_value=[course]), patch.object(
            progress_service.material_repository, "list_uploaded_materials", return_value=[]
        ), patch.object(
            progress_service.assessment_repository, "list_categories", return_value=[category]
        ):
            learner = progress_service.my_progress(
                self.base.user,
                area="internal",
                group="grpBio",
            )

        visible = [item for item in learner["records"] if item.get("id") == record_id]
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["reviewStatus"], "completed")
        self.assertEqual(visible[0]["reviewerName"], "王老師")
        self.assertEqual(visible[0]["evaluatorTitle"], "資深醫檢師")
        self.assertTrue(learner["courses"][0]["completed"])
        self.assertTrue(learner["courses"][0]["examPassed"])


if __name__ == "__main__":
    unittest.main()
