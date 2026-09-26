import datetime as dt
import unittest
from unittest.mock import patch

from teacher_app.common.errors import ApiError
from teacher_app.learning import compliance_service


NOW = dt.datetime(2026, 9, 26, 6, 0, tzinfo=dt.timezone.utc)


def learner(username="lab01", group="grpBio"):
    return {
        "username": username,
        "name": "王小明",
        "empId": "E001",
        "role": "student",
        "roles": ["student"],
        "preferredArea": "internal",
        "preferredGroup": group,
        "active": True,
    }


def manager(role="education_admin", group="grpBio"):
    return {
        "username": "manager",
        "name": "管理者",
        "empId": "M001",
        "role": role,
        "roles": [role],
        "preferredArea": "internal",
        "preferredGroup": group,
    }


class TrainingComplianceTests(unittest.TestCase):
    def _assignment(self, **updates):
        value = {
            "id": "la-1",
            "courseId": "course-1",
            "required": True,
            "dueAt": "2026-09-30T00:00:00+00:00",
            "assignedAt": "2026-09-01T00:00:00+00:00",
            "sourceAssignmentIds": ["la-1"],
        }
        value.update(updates)
        return value

    def _progress(self, **course_updates):
        course = {
            "id": "course-1",
            "title": "血庫安全",
            "materialsCompleted": 1,
            "materialsTotal": 2,
            "materialsComplete": False,
            "examRequired": True,
            "examPassed": False,
            "requiredMaterialIds": ["m1", "m2"],
            "requiredExamIds": ["exam-1"],
            "completed": False,
        }
        course.update(course_updates)
        return {"courses": [course], "materialsRetraining": [], "records": []}

    def _build(self, progress=None, assignment=None, certificates=None, actor=None):
        with (
            patch(
                "teacher_app.learning.compliance_service.accounts.list_accounts",
                return_value=[learner()],
            ),
            patch(
                "teacher_app.learning.compliance_service.assignment_service.list_for_user",
                return_value=[assignment or self._assignment()],
            ),
            patch(
                "teacher_app.learning.compliance_service.progress_service.my_progress",
                return_value=progress or self._progress(),
            ),
            patch(
                "teacher_app.learning.compliance_service.certificate_service.list_certificates",
                return_value=certificates or [],
            ),
        ):
            return compliance_service.build_matrix(
                actor or manager(), area="internal", group="grpBio", now=NOW
            )

    def test_in_progress_projection(self):
        payload = self._build()
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["rows"][0]["status"], "in_progress")

    def test_overdue_precedes_other_incomplete_states(self):
        payload = self._build(
            assignment=self._assignment(dueAt="2026-09-20T00:00:00+00:00")
        )
        self.assertEqual(payload["rows"][0]["status"], "overdue")

    def test_retraining_uses_existing_stale_material_projection(self):
        progress = self._progress()
        progress["materialsRetraining"] = ["m2"]
        payload = self._build(progress=progress)
        self.assertEqual(payload["rows"][0]["status"], "retraining")
        self.assertTrue(payload["rows"][0]["retrainingRequired"])

    def test_failed_final_exam_projects_remediation(self):
        progress = self._progress(materialsCompleted=2, materialsComplete=True)
        progress["records"] = [
            {
                "courseId": "course-1",
                "quizCategoryId": "exam-1",
                "reviewStatus": "completed",
                "score": 60,
                "passingScore": 80,
            }
        ]
        payload = self._build(progress=progress)
        self.assertEqual(payload["rows"][0]["status"], "remediation")

    def test_completed_row_reports_current_certificate(self):
        progress = self._progress(
            materialsCompleted=2,
            materialsComplete=True,
            examPassed=True,
            completed=True,
        )
        payload = self._build(
            progress=progress,
            certificates=[
                {
                    "id": "CERT-1",
                    "courseId": "course-1",
                    "currentValid": True,
                    "issuedAt": "2026-09-25T00:00:00+00:00",
                }
            ],
        )
        row = payload["rows"][0]
        self.assertEqual(row["status"], "complete")
        self.assertEqual(row["certificateStatus"], "current")

    def test_group_leader_cannot_cross_group(self):
        with self.assertRaises(ApiError) as caught:
            compliance_service.build_matrix(
                manager("group_leader"), area="internal", group="grpBB", now=NOW
            )
        self.assertEqual(caught.exception.status, 403)

    def test_status_filter_is_applied(self):
        with (
            patch(
                "teacher_app.learning.compliance_service.accounts.list_accounts",
                return_value=[learner()],
            ),
            patch(
                "teacher_app.learning.compliance_service.assignment_service.list_for_user",
                return_value=[self._assignment()],
            ),
            patch(
                "teacher_app.learning.compliance_service.progress_service.my_progress",
                return_value=self._progress(),
            ),
            patch(
                "teacher_app.learning.compliance_service.certificate_service.list_certificates",
                return_value=[],
            ),
        ):
            payload = compliance_service.build_matrix(
                manager(), status="complete", now=NOW
            )
        self.assertEqual(payload["rows"], [])


if __name__ == "__main__":
    unittest.main()
