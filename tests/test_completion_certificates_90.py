import json
import sqlite3
import unittest
from unittest.mock import patch

from teacher_app.common.errors import ApiError
from teacher_app.learning import certificate_service
from teacher_app.maintenance.completion_certificate_migration import completion_certificates_90


USER = {
    "username": "learner1",
    "empId": "E001",
    "name": "王小明",
    "preferredArea": "internal",
    "preferredGroup": "grpBB",
}

COURSE = {
    "id": "course-1",
    "title": "輸血安全",
    "area": "internal",
    "group": "grpBB",
    "active": True,
}

MATERIAL = {
    "id": "mat-1",
    "title": "輸血 SOP",
    "courseId": "course-1",
    "area": "internal",
    "group": "grpBB",
    "active": True,
    "currentVersion": 3,
    "requiredCompletionVersion": 3,
}

EXAM = {
    "id": "exam-1",
    "title": "輸血安全考核",
    "courseId": "course-1",
    "area": "internal",
    "group": "grpBB",
    "active": True,
}


def progress(completed=True):
    return {
        "courses": [{
            **COURSE,
            "completed": completed,
            "materialsTotal": 1,
            "materialsCompleted": 1 if completed else 0,
            "materialsComplete": completed,
            "examRequired": True,
            "examPassed": completed,
            "requiredMaterialIds": ["mat-1"],
            "requiredExamIds": ["exam-1"],
            "examMode": "any",
        }],
        "materialsCompleted": {"mat-1": "2026-09-25T10:00:00+00:00"} if completed else {},
        "records": [{
            "id": "record-1",
            "quizCategoryId": "exam-1",
            "courseId": "course-1",
            "reviewStatus": "completed",
            "score": 90,
            "passingScore": 80,
            "timestamp": "2026-09-25T10:30:00+00:00",
        }] if completed else [],
    }


def requirement_fingerprint(version=3):
    return certificate_service._requirement_fingerprint({
        "courseId": "course-1",
        "materials": [{"id": "mat-1", "requiredCompletionVersion": version}],
        "requiredExamIds": ["exam-1"],
        "examMode": "any",
    })


class CompletionCertificate90Tests(unittest.TestCase):
    def test_migration_creates_append_only_certificate_store(self):
        conn = sqlite3.connect(":memory:")
        try:
            completion_certificates_90(conn, "sqlite")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(course_completion_certificates)")}
            self.assertIn("completion_fingerprint", columns)
            self.assertIn("evidence_json", columns)
            indexes = {row[1] for row in conn.execute("PRAGMA index_list(course_completion_certificates)")}
            self.assertTrue(any("sqlite_autoindex" in name for name in indexes))
        finally:
            conn.close()

    def _common_patches(self, *, completed=True, assignments=None):
        return (
            patch("teacher_app.learning.certificate_service.course_repository.get_course", return_value=COURSE),
            patch("teacher_app.learning.certificate_service.learning_access.can_access_learning_item", return_value=True),
            patch("teacher_app.learning.certificate_service.assignment_service.list_for_user", return_value=assignments or []),
            patch("teacher_app.learning.certificate_service.progress_service.my_progress", return_value=progress(completed)),
            patch("teacher_app.learning.certificate_service.material_repository.list_uploaded_materials", return_value=[MATERIAL]),
            patch("teacher_app.learning.certificate_service.assessment_repository.list_categories", return_value=[EXAM]),
            patch("teacher_app.learning.certificate_service.certificate_repository.list_material_completion_rows", return_value=[{
                "material_id": "mat-1", "completed_at": "2026-09-25T10:00:00+00:00", "completed_version": 3,
            }]),
        )

    def test_incomplete_course_cannot_issue_certificate(self):
        patches = self._common_patches(completed=False)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patch(
            "teacher_app.learning.certificate_service.certificate_repository.find_for_fingerprint",
            return_value=None,
        ):
            with self.assertRaises(ApiError) as caught:
                certificate_service.issue_certificate(USER, "course-1")
        self.assertEqual(caught.exception.code, "COURSE_NOT_COMPLETE")
        self.assertEqual(caught.exception.status, 409)

    def test_same_completion_requirement_returns_existing_certificate(self):
        existing = {
            "id": "CERT-OLD",
            "username": "learner1",
            "courseId": "course-1",
            "courseTitle": "輸血安全",
            "completionFingerprint": requirement_fingerprint(),
            "evidence": {},
        }
        patches = self._common_patches(completed=True)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patch(
            "teacher_app.learning.certificate_service.certificate_repository.find_for_fingerprint",
            return_value=existing,
        ), patch(
            "teacher_app.learning.certificate_service.certificate_repository.insert_certificate"
        ) as insert:
            result = certificate_service.issue_certificate(USER, "course-1")
        self.assertFalse(result["issued"])
        self.assertEqual(result["certificate"]["id"], "CERT-OLD")
        self.assertTrue(result["certificate"]["currentValid"])
        insert.assert_not_called()

    def test_new_completion_requirement_inserts_certificate(self):
        inserted = {
            "id": "CERT-NEW",
            "username": "learner1",
            "courseId": "course-1",
            "courseTitle": "輸血安全",
            "completionFingerprint": requirement_fingerprint(),
            "evidence": {},
        }
        patches = self._common_patches(completed=True)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patch(
            "teacher_app.learning.certificate_service.certificate_repository.find_for_fingerprint",
            return_value=None,
        ), patch(
            "teacher_app.learning.certificate_service.certificate_repository.insert_certificate",
            return_value=inserted,
        ) as insert:
            result = certificate_service.issue_certificate(USER, "course-1")
        self.assertTrue(result["issued"])
        self.assertEqual(result["certificate"]["id"], "CERT-NEW")
        evidence = json.loads(insert.call_args.args[0]["evidence_json"])
        self.assertEqual(evidence["materials"][0]["completedVersion"], 3)
        self.assertEqual(evidence["exams"][0]["recordId"], "record-1")

    def test_requirement_fingerprint_changes_with_retraining_version(self):
        self.assertNotEqual(requirement_fingerprint(2), requirement_fingerprint(3))

    def test_assignment_mode_denies_unassigned_course(self):
        patches = self._common_patches(completed=True, assignments=[{"courseId": "other-course"}])
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with self.assertRaises(ApiError) as caught:
                certificate_service.issue_certificate(USER, "course-1")
        self.assertEqual(caught.exception.code, "COURSE_NOT_ASSIGNED")
        self.assertEqual(caught.exception.status, 403)


if __name__ == "__main__":
    unittest.main()
