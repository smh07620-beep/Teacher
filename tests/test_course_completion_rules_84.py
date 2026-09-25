import unittest

from teacher_app.learning.completion import evaluate_course_completion, normalize_policy


MATERIALS = [{"id": "m1"}, {"id": "m2"}]
EXAMS = [{"id": "q1"}, {"id": "q2"}]


class CourseCompletionRulesTests(unittest.TestCase):
    def test_legacy_default_requires_all_materials_and_any_exam(self):
        result = evaluate_course_completion(
            materials=MATERIALS,
            exams=EXAMS,
            completed_material_ids={"m1", "m2"},
            passed_exam_ids={"q2"},
        )
        self.assertTrue(result["completed"])
        self.assertEqual(result["materialsCompleted"], 2)
        self.assertEqual(result["examMode"], "any")

    def test_missing_material_keeps_course_incomplete(self):
        result = evaluate_course_completion(
            materials=MATERIALS,
            exams=EXAMS,
            completed_material_ids={"m1"},
            passed_exam_ids={"q1"},
        )
        self.assertFalse(result["completed"])

    def test_all_exam_mode_requires_every_configured_exam(self):
        policy = {"examMode": "all", "requiredExamIds": ["q1", "q2"]}
        partial = evaluate_course_completion(
            materials=MATERIALS,
            exams=EXAMS,
            completed_material_ids={"m1", "m2"},
            passed_exam_ids={"q1"},
            policy=policy,
        )
        self.assertFalse(partial["completed"])
        complete = evaluate_course_completion(
            materials=MATERIALS,
            exams=EXAMS,
            completed_material_ids={"m1", "m2"},
            passed_exam_ids={"q1", "q2"},
            policy=policy,
        )
        self.assertTrue(complete["completed"])

    def test_explicit_material_subset_supports_future_required_optional_split(self):
        result = evaluate_course_completion(
            materials=MATERIALS,
            exams=[],
            completed_material_ids={"m1"},
            passed_exam_ids=set(),
            policy={"requiredMaterialIds": ["m1"]},
        )
        self.assertTrue(result["completed"])
        self.assertEqual(result["materialsTotal"], 1)

    def test_exam_none_allows_material_only_course(self):
        result = evaluate_course_completion(
            materials=MATERIALS,
            exams=EXAMS,
            completed_material_ids={"m1", "m2"},
            passed_exam_ids=set(),
            policy={"examMode": "none"},
        )
        self.assertTrue(result["completed"])
        self.assertFalse(result["examRequired"])

    def test_invalid_policy_falls_back_safely(self):
        policy = normalize_policy({"examMode": "bogus", "requiredMaterialIds": "m1"})
        self.assertEqual(policy["examMode"], "any")
        self.assertEqual(policy["requiredMaterialIds"], [])


if __name__ == "__main__":
    unittest.main()
