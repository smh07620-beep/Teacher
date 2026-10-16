"""Reader rules v2 + exam unlock gate (2026-10-16 overhaul, batch 1)."""
import unittest
from unittest.mock import patch

from teacher_app.common.errors import ApiError
from teacher_app.learning import content, gate


class DwellRuleTests(unittest.TestCase):
    def test_min_dwell_scales_with_text_and_caps(self):
        self.assertEqual(content.min_dwell_seconds(0), 5)
        self.assertEqual(content.min_dwell_seconds(250), 15)
        self.assertEqual(content.min_dwell_seconds(99999), 30)
        self.assertEqual(content.min_dwell_seconds(500, override=3), 3)

    def test_client_cannot_inflate_dwell(self):
        clamped = content.clamp_dwell_delta({"1": 600, "2": 600}, elapsed_seconds=10)
        self.assertAlmostEqual(sum(clamped.values()), 15.0)

    def test_rapid_click_through_is_not_complete(self):
        result = content.document_completion_v2(3, {"1": 1, "2": 1, "3": 1}, {"1": 5, "2": 5, "3": 5})
        self.assertFalse(result["completed"])
        full = content.document_completion_v2(3, {"1": 6, "2": 9, "3": 5}, {"1": 5, "2": 5, "3": 5})
        self.assertTrue(full["completed"])

    def test_seek_to_end_gets_few_buckets(self):
        credited = content.limit_new_buckets(range(0, 60), [], elapsed_seconds=5)
        self.assertEqual(len(credited), 2)


class GateTests(unittest.TestCase):
    student = {"username": "s1", "role": "student", "roles": ["student"]}

    def _patch(self, materials, rows):
        return (
            patch.object(gate.material_repository, "list_uploaded_materials", return_value=materials),
            patch.object(gate.learning_repository, "list_progress_for_user", return_value=rows),
            patch.object(gate.learning_access, "is_assignment_gated", return_value=True),
        )

    def test_locked_until_required_materials_done(self):
        materials = [{"id": "m1", "courseId": "c1"}, {"id": "m2", "courseId": "c1"}]
        rows = [{"material_id": "m1", "completed": 1, "completed_version": 1}]
        a, b, c = self._patch(materials, rows)
        with a, b, c:
            state = gate.exam_unlock_state(self.student, "c1")
        self.assertFalse(state["unlocked"])
        self.assertEqual(state["progress"], 50)
        self.assertEqual(state["missing"], ["m2"])

    def test_optional_and_empty_course_do_not_block(self):
        materials = [{"id": "m1", "courseId": "c1", "storageMeta": {"optional": True}}]
        a, b, c = self._patch(materials, [])
        with a, b, c:
            self.assertTrue(gate.exam_unlock_state(self.student, "c1")["unlocked"])
            self.assertTrue(gate.exam_unlock_state(self.student, "none")["unlocked"])

    def test_preview_roles_are_not_gated(self):
        with patch.object(gate.learning_access, "is_assignment_gated", return_value=False):
            self.assertTrue(gate.exam_unlock_state({"username": "t"}, "c1")["unlocked"])

    def test_start_attempt_raises_materials_not_complete(self):
        from teacher_app.exams import service

        locked = {"unlocked": False, "progress": 60, "missing": ["m2"], "reason": "讀完教材後解鎖（目前 60%）"}
        category = {"id": "q1", "courseId": "c1", "active": True}
        with patch.object(service, "assert_exam_open"), \
             patch.object(service.assessment_repository, "get_category_full", return_value=category), \
             patch("teacher_app.assessments.assignees.assert_can_take"), \
             patch("teacher_app.learning.access.student_may_see_course", return_value=True), \
             patch.object(gate, "exam_unlock_state", return_value=locked):
            with self.assertRaises(ApiError) as caught:
                service.start_attempt({"username": "s1", "role": "student"}, {"quizCategoryId": "q1"})
        self.assertEqual(caught.exception.code, "MATERIALS_NOT_COMPLETE")
        self.assertEqual(caught.exception.status, 403)


if __name__ == "__main__":
    unittest.main()


class ReviewPagesTests(unittest.TestCase):
    def test_pages_by_material_uses_wrong_page_anchored_questions(self):
        from teacher_app.learning import review_pages

        questions = [
            {"isCorrect": False, "reviewSource": {"materialId": "m1", "page": 4}},
            {"isCorrect": False, "reviewSource": {"materialId": "m1", "page": 7}},
            {"isCorrect": True, "reviewSource": {"materialId": "m1", "page": 9}},
            {"isCorrect": False, "reviewSource": {"materialId": "m2", "timeSeconds": 30}},
        ]
        self.assertEqual(review_pages.pages_by_material(questions), {"m1": [4, 7]})

    def test_advance_clears_pages_only_after_required_dwell(self):
        from teacher_app.learning import review_pages

        position = {"reviewPages": [4, 7], "reviewDwell": {}}
        review_pages.advance(position, 4, {"4": 3}, {"4": 5, "7": 5}, True)
        self.assertEqual(position["reviewPages"], [4, 7])
        review_pages.advance(position, 4, {"4": 3}, {"4": 5, "7": 5}, True)
        self.assertEqual(position["reviewPages"], [7])

    def test_v1_visit_clears_page(self):
        from teacher_app.learning import review_pages

        position = {"reviewPages": [4, 7]}
        review_pages.advance(position, 7, {}, {}, False)
        self.assertEqual(position["reviewPages"], [4])

    def test_pending_review_pages_keep_exam_locked(self):
        materials = [{"id": "m1", "courseId": "c1"}]
        rows = [{"material_id": "m1", "completed": 1, "completed_version": 1,
                 "position": '{"reviewPages": [4]}'}]
        with patch.object(gate.material_repository, "list_uploaded_materials", return_value=materials), \
             patch.object(gate.learning_repository, "list_progress_for_user", return_value=rows), \
             patch.object(gate.learning_access, "is_assignment_gated", return_value=True):
            state = gate.exam_unlock_state({"username": "s1"}, "c1")
        self.assertFalse(state["unlocked"])


class AccessExplainTests(unittest.TestCase):
    def test_unassigned_student_is_blocked_and_reason_names_assignment(self):
        from teacher_app.learning import access_explain

        user = {"username": "s1", "role": "student", "roles": ["student"], "active": True,
                "preferredArea": "internal", "preferredGroup": "grpBio"}
        course = {"id": "c1", "area": "internal", "group": "grpBio", "active": True, "lifecycleStatus": "published"}
        with patch.object(access_explain.access, "assigned_course_ids", return_value=frozenset()), \
             patch("teacher_app.courses.repository.get_course", return_value=course):
            result = access_explain.explain(user, "course", course, learner_view=True)
        self.assertFalse(result["allowed"])
        self.assertIn("課程指派", result["blocker"])

    def test_assigned_student_is_allowed(self):
        from teacher_app.learning import access_explain

        user = {"username": "s1", "role": "student", "roles": ["student"], "active": True,
                "preferredArea": "internal", "preferredGroup": "grpBio"}
        course = {"id": "c1", "area": "internal", "group": "grpBio", "active": True, "lifecycleStatus": "published"}
        with patch.object(access_explain.access, "assigned_course_ids", return_value=frozenset({"c1"})):
            result = access_explain.explain(user, "course", course, learner_view=True)
        self.assertTrue(result["allowed"])
