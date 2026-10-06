import datetime as dt
import unittest
from pathlib import Path
from unittest.mock import patch

from pgy_frontend import ASSET_MANIFEST
from teacher_app.command_center import service


ROOT = Path(__file__).parents[1]


class TeacherActionQueue1024Tests(unittest.TestCase):
    def setUp(self):
        self.user = {
            "username": "leader-bio",
            "name": "生化組長",
            "role": "group_leader",
            "roles": ["group_leader"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }
        self.now = dt.datetime(2026, 10, 1, 8, 0, tzinfo=dt.timezone.utc)

    def test_teacher_queue_converges_four_scoped_sources(self):
        records = [
            {"id": "r-bio", "reviewStatus": "pending", "quizTitle": "生化申論", "name": "學員甲", "trainingArea": "internal", "groupKey": "grpBio"},
            {"id": "r-micro", "reviewStatus": "pending", "quizTitle": "細菌申論", "name": "學員乙", "trainingArea": "internal", "groupKey": "grpMicro"},
        ]
        jobs = [
            {"id": "job-bio", "status": "failed"},
            {"id": "job-bio-lost", "status": "failed"},
            {"id": "job-micro", "status": "failed"},
        ]
        full_jobs = {
            "job-bio": {"id": "job-bio", "status": "failed", "error": "轉檔失敗", "stagingBackend": "r2", "stagingKey": "staging/bio", "payload": {"title": "生化教材", "area": "internal", "group": "grpBio"}},
            "job-bio-lost": {"id": "job-bio-lost", "status": "failed", "error": "舊檔已清理", "payload": {"title": "舊生化教材", "area": "internal", "group": "grpBio"}},
            "job-micro": {"id": "job-micro", "status": "failed", "error": "轉檔失敗", "payload": {"title": "細菌教材", "area": "internal", "group": "grpMicro"}},
        }
        assignments = [
            {"id": "a-soon", "courseId": "course-bio", "area": "internal", "group": "grpBio", "dueAt": "2026-10-05T08:00:00+00:00"},
            {"id": "a-later", "courseId": "course-bio", "area": "internal", "group": "grpBio", "dueAt": "2026-11-05T08:00:00+00:00"},
        ]
        courses = [
            {"id": "course-bio", "title": "生化草稿", "area": "internal", "group": "grpBio", "active": False},
            {"id": "course-micro", "title": "細菌草稿", "area": "internal", "group": "grpMicro", "active": False},
            {"id": "course-live", "title": "已發布課程", "area": "internal", "group": "grpBio", "active": True},
        ]

        def visible(_user, item):
            return str(item.get("area") or "") == "internal" and str(item.get("group") or "") == "grpBio"

        def can_review(_user, record):
            return record.get("id") == "r-bio"

        with patch.object(service.audience, "current_profile", return_value={"audience": "online", "pgyLearner": False}), \
             patch.object(service.exam_records, "list_records", return_value=records), \
             patch.object(service.exam_records, "can_review_record", side_effect=can_review) as review_scope, \
             patch.object(service.worker_repository, "list_material_jobs", return_value=jobs), \
             patch.object(service.worker_repository, "get_material_job", side_effect=lambda job_id, include_payload=True: full_jobs[job_id]), \
             patch.object(service.assignment_service, "admin_list", return_value=assignments), \
             patch.object(service.course_repository, "get_course", return_value={"id": "course-bio", "title": "生化訓練", "area": "internal", "group": "grpBio"}), \
             patch.object(service.course_repository, "list_courses", return_value=courses), \
             patch.object(service.learning_access, "can_access_learning_item", side_effect=visible):
            result = service.build_summary(self.user, now=self.now)

        teacher_items = [item for item in result["items"] if item.get("domain") != "pgy"]
        self.assertEqual(result["counts"]["teacher"], 4)
        self.assertEqual(result["counts"]["review"], 1)
        self.assertEqual(result["counts"]["materialFailure"], 1)
        self.assertEqual(result["counts"]["due"], 1)
        self.assertEqual(result["counts"]["draft"], 1)
        self.assertEqual({item["kind"] for item in teacher_items}, {"review", "material_failure", "due", "draft"})
        self.assertNotIn("r-micro", {item["id"] for item in teacher_items})
        self.assertNotIn("job-micro", {item["id"] for item in teacher_items})
        self.assertNotIn("job-bio-lost", {item["id"] for item in teacher_items})
        self.assertNotIn("course-micro", {item["id"] for item in teacher_items})
        self.assertEqual(review_scope.call_count, 2)

        review = next(item for item in teacher_items if item["kind"] == "review")
        failure = next(item for item in teacher_items if item["kind"] == "material_failure")
        due = next(item for item in teacher_items if item["kind"] == "due")
        draft = next(item for item in teacher_items if item["kind"] == "draft")
        self.assertEqual(review["resourceId"], "r-bio")
        self.assertEqual(failure["resourceId"], "job-bio")
        self.assertTrue(failure["sourceRetained"])
        self.assertEqual(failure["actionLabel"], "直接重新處理")
        self.assertEqual(due["courseId"], "course-bio")
        self.assertEqual(due["resourceId"], "course-bio")
        self.assertEqual(draft["courseId"], "course-bio")
        self.assertEqual(draft["resourceId"], "course-bio")

    def test_material_failures_without_retained_source_stay_out_of_needs_action(self):
        jobs = [{"id": "job-gone", "status": "failed"}]
        full = {
            "id": "job-gone",
            "status": "failed",
            "error": "MEGA 登入失敗",
            "stagingBackend": "",
            "stagingKey": "",
            "payload": {"title": "已無原始檔教材", "area": "internal", "group": "grpBio"},
        }
        with patch.object(service.worker_repository, "list_material_jobs", return_value=jobs), \
             patch.object(service.worker_repository, "get_material_job", return_value=full), \
             patch.object(service.learning_access, "can_access_learning_item", return_value=True):
            values = service._teacher_material_failure_items(self.user)
        self.assertEqual(values, [])

    def test_review_queue_fails_closed_when_record_scope_is_not_authorized(self):
        teacher = {
            "username": "teacher2",
            "name": "未指派教師",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }
        records = [
            {"id": "r-unassigned", "reviewStatus": "pending", "quizTitle": "同組但未指派", "name": "學員甲", "empId": "S001", "trainingArea": "internal", "groupKey": "grpBio"},
        ]
        with patch.object(service.audience, "current_profile", return_value={"audience": "online", "pgyLearner": False}), \
             patch.object(service.exam_records, "list_records", return_value=records), \
             patch.object(service.exam_records, "can_review_record", return_value=False) as review_scope, \
             patch.object(service.worker_repository, "list_material_jobs", return_value=[]), \
             patch.object(service.course_repository, "list_courses", return_value=[]):
            result = service.build_summary(teacher, now=self.now)
        self.assertEqual(result["counts"]["review"], 0)
        self.assertEqual(result["counts"]["teacher"], 0)
        self.assertFalse(any(item.get("resourceId") == "r-unassigned" for item in result["items"]))
        review_scope.assert_called_once_with(teacher, records[0])

    def test_student_never_receives_teacher_queue(self):
        student = {"username": "s1", "role": "student", "roles": ["student"], "name": "學員", "empId": "E1"}
        with patch.object(service.audience, "current_profile", return_value={"audience": "online", "pgyLearner": False}), \
             patch.object(service.exam_records, "list_records") as records, \
             patch.object(service.worker_repository, "list_material_jobs") as jobs:
            result = service.build_summary(student, now=self.now)
        self.assertEqual(result["counts"]["teacher"], 0)
        records.assert_not_called()
        jobs.assert_not_called()

    def test_ui_is_loaded_after_product_convergence_and_has_no_admin_key_seam(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertIn("/teacher-action-queue-1024.js", body)
        self.assertLess(body.index("/product-convergence-101.js"), body.index("/teacher-action-queue-1024.js"))
        source = ROOT.joinpath("static", "teacher-action-queue-1024.js").read_text(encoding="utf-8")
        for phrase in (
            "需要我處理",
            "待批改",
            "教材需要處理",
            "未發布草稿",
            "/api/training-command-center",
            "switchTeacherMode?.('scoring')",
            "openEssayReview",
            "renderMaterialJobs",
            "data-learning-assign-course",
            "teachingEditCourse",
            "renderAdminCourseMaterialHub",
            "retryMaterialJob",
            "重新排隊中…",
        ):
            self.assertIn(phrase, source)
        self.assertNotIn("X-Admin-Key", source)
        self.assertNotIn("getAdminKey", source)
        self.assertNotIn("localStorage", source)
        self.assertIn("✓ 目前沒有需要你處理的項目。", source)
        self.assertIn("查看其餘", source)
        self.assertNotIn("今天先處理第一順位", source)

    def test_material_failure_action_delegates_to_canonical_retry_owner(self):
        source = ROOT.joinpath("static", "teacher-action-queue-1024.js").read_text(encoding="utf-8")
        self.assertIn("item.sourceRetained && wanted && typeof window.retryMaterialJob === 'function'", source)
        self.assertIn("const retried = await window.retryMaterialJob(wanted)", source)
        self.assertIn("if (retried !== false)", source)
        jobs_source = ROOT.joinpath("static", "admin-jobs.js").read_text(encoding="utf-8")
        self.assertIn("credentials:'same-origin'", jobs_source)
        self.assertIn("return true", jobs_source)
        self.assertIn("return false", jobs_source)
        self.assertIn("TeacherActionQueue1024?.refresh?.()", jobs_source)

    def test_queue_mounts_in_the_active_teacher_workspace_and_filters_context(self):
        source = ROOT.joinpath("static", "teacher-action-queue-1024.js").read_text(encoding="utf-8")
        for phrase in (
            "function currentContext()",
            "admin-section-content",
            "admin-section-quiz",
            "admin-section-results",
            "item.kind === 'review'",
            "item.kind !== 'review'",
            "section.dataset.productSection = 'needs-action'",
        ):
            self.assertIn(phrase, source)

    def test_review_ui_uses_server_derived_reviewer_identity(self):
        source = ROOT.joinpath("static", "admin-results.js").read_text(encoding="utf-8")
        self.assertIn("完成批改時由目前登入教師自動帶入", source)
        self.assertIn("reviewerInput.disabled = true", source)
        self.assertNotIn("請填寫批改者姓名", source)
        self.assertNotIn("reviewerName,", source)
        self.assertIn("TeacherActionQueue1024?.refresh?.()", source)


if __name__ == "__main__":
    unittest.main()