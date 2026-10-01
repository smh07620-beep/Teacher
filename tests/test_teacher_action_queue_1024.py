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
            {"id": "job-micro", "status": "failed"},
        ]
        full_jobs = {
            "job-bio": {"id": "job-bio", "status": "failed", "error": "轉檔失敗", "stagingBackend": "r2", "stagingKey": "staging/bio", "payload": {"title": "生化教材", "area": "internal", "group": "grpBio"}},
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

        with patch.object(service.audience, "current_profile", return_value={"audience": "online", "pgyLearner": False}), \
             patch.object(service.exam_records, "list_records", return_value=records), \
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
        self.assertNotIn("course-micro", {item["id"] for item in teacher_items})
        failure = next(item for item in teacher_items if item["kind"] == "material_failure")
        self.assertTrue(failure["sourceRetained"])

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
        for phrase in ("需要我處理", "待批改", "教材需要處理", "未發布草稿", "/api/training-command-center"):
            self.assertIn(phrase, source)
        self.assertNotIn("X-Admin-Key", source)
        self.assertNotIn("getAdminKey", source)
        self.assertNotIn("localStorage", source)


if __name__ == "__main__":
    unittest.main()
