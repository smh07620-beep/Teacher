import datetime as dt
import unittest
from unittest.mock import patch

from teacher_app.learning import compliance_service


NOW = dt.datetime(2026, 9, 26, 6, 0, tzinfo=dt.timezone.utc)


def learner():
    return {
        "username": "lab01",
        "name": "王小明",
        "empId": "E001",
        "role": "student",
        "roles": ["student"],
        "preferredArea": "internal",
        "preferredGroup": "grpBio",
        "active": True,
    }


def manager():
    return {
        "username": "manager",
        "name": "管理者",
        "empId": "M001",
        "role": "education_admin",
        "roles": ["education_admin"],
        "preferredArea": "internal",
        "preferredGroup": "grpBio",
    }


class TrainingCompetencyEvidence92Tests(unittest.TestCase):
    def _assignment(self):
        return {
            "id": "la-1",
            "courseId": "course-1",
            "required": True,
            "dueAt": "2026-09-30T00:00:00+00:00",
            "assignedAt": "2026-09-01T00:00:00+00:00",
            "sourceAssignmentIds": ["la-1"],
        }

    def _progress(self, *, materials_completed=0, completed=False, exam_passed=False, records=None):
        return {
            "courses": [
                {
                    "id": "course-1",
                    "title": "血庫安全",
                    "materialsCompleted": materials_completed,
                    "materialsTotal": 2,
                    "materialsComplete": materials_completed >= 2,
                    "examRequired": True,
                    "examPassed": exam_passed,
                    "requiredMaterialIds": ["m1", "m2"],
                    "requiredExamIds": ["exam-1"],
                    "completed": completed,
                }
            ],
            "materialsRetraining": [],
            "records": list(records or []),
        }

    def _build(self, progress, *, certificates=None):
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
                return_value=progress,
            ),
            patch(
                "teacher_app.learning.compliance_service.certificate_service.list_certificates",
                return_value=list(certificates or []),
            ),
        ):
            return compliance_service.build_matrix(
                manager(), area="internal", group="grpBio", now=NOW
            )

    def test_untrained_and_training_are_distinct(self):
        untrained = self._build(self._progress(materials_completed=0))["rows"][0]
        training = self._build(self._progress(materials_completed=1))["rows"][0]
        self.assertEqual(untrained["qualificationStatus"], "untrained")
        self.assertEqual(training["qualificationStatus"], "training")

    def test_pending_review_projects_safe_assessment_evidence(self):
        progress = self._progress(
            materials_completed=2,
            records=[
                {
                    "id": "record-1",
                    "courseId": "course-1",
                    "quizCategoryId": "exam-1",
                    "reviewStatus": "pending",
                    "score": 88,
                    "passingScore": 80,
                    "timestamp": "2026-09-25T08:00:00+00:00",
                    "reviewedAt": "",
                    "reviewerName": "",
                    "reviewComment": "",
                    "evaluatorName": "李老師",
                    "evaluatorTitle": "組長",
                    "publicationId": "pub-1",
                    "publicationHash": "hash-1",
                    "answersDetail": [{"question": "must not leak"}],
                }
            ],
        )
        row = self._build(progress)["rows"][0]
        self.assertEqual(row["qualificationStatus"], "pending_review")
        evidence = row["evidence"]["exam"]
        self.assertEqual(evidence["recordId"], "record-1")
        self.assertEqual(evidence["evaluatorName"], "李老師")
        self.assertEqual(evidence["evaluatorTitle"], "組長")
        self.assertEqual(evidence["score"], 88)
        self.assertNotIn("answersDetail", evidence)

    def test_latest_review_metadata_is_exposed_for_traceability(self):
        progress = self._progress(
            materials_completed=2,
            records=[
                {
                    "id": "older",
                    "courseId": "course-1",
                    "quizCategoryId": "exam-1",
                    "reviewStatus": "completed",
                    "score": 60,
                    "passingScore": 80,
                    "timestamp": "2026-09-20T08:00:00+00:00",
                    "reviewedAt": "2026-09-20T09:00:00+00:00",
                    "reviewerName": "舊評核者",
                    "reviewComment": "舊評語",
                },
                {
                    "id": "newer",
                    "courseId": "course-1",
                    "quizCategoryId": "exam-1",
                    "reviewStatus": "completed",
                    "score": 70,
                    "passingScore": 80,
                    "timestamp": "2026-09-25T08:00:00+00:00",
                    "reviewedAt": "2026-09-25T09:00:00+00:00",
                    "reviewerName": "陳老師",
                    "reviewComment": "請補強後再評核",
                },
            ],
        )
        row = self._build(progress)["rows"][0]
        evidence = row["evidence"]["exam"]
        self.assertEqual(row["qualificationStatus"], "remediation")
        self.assertEqual(evidence["recordId"], "newer")
        self.assertEqual(evidence["reviewerName"], "陳老師")
        self.assertEqual(evidence["reviewComment"], "請補強後再評核")
        self.assertEqual(evidence["reviewedAt"], "2026-09-25T09:00:00+00:00")

    def test_passed_status_and_certificate_evidence(self):
        payload = self._build(
            self._progress(materials_completed=2, completed=True, exam_passed=True),
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
        self.assertEqual(row["qualificationStatus"], "passed")
        self.assertEqual(row["evidence"]["certificate"]["id"], "CERT-1")
        self.assertEqual(row["evidence"]["certificate"]["status"], "current")
        self.assertEqual(payload["summary"]["qualification"]["passed"], 1)


if __name__ == "__main__":
    unittest.main()
