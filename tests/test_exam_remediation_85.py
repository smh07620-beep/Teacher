import unittest

from teacher_app.exams import remediation


class ExamRemediation85Tests(unittest.TestCase):
    def setUp(self):
        self.materials = [
            {
                "id": "sop-1", "title": "輸血 SOP", "materialType": "sop",
                "courseId": "course-1", "category": "quiz-1", "area": "internal",
                "group": "grpBB", "active": True, "currentVersion": 3,
                "requiredCompletionVersion": 3,
            },
            {
                "id": "guide-1", "title": "抗體鑑定教材", "materialType": "standard",
                "courseId": "course-1", "category": "", "area": "internal",
                "group": "grpBB", "active": True, "currentVersion": 1,
                "requiredCompletionVersion": 1,
            },
            {
                "id": "other-group", "title": "血液組教材", "materialType": "sop",
                "courseId": "course-1", "category": "quiz-1", "area": "internal",
                "group": "grpHema", "active": True,
            },
            {
                "id": "other-course", "title": "其他課程", "materialType": "sop",
                "courseId": "course-2", "category": "quiz-2", "area": "internal",
                "group": "grpBB", "active": True,
            },
        ]

    def test_failed_exam_builds_same_scope_course_review_plan(self):
        plan = remediation.build_plan(
            score=65, passing_score=80, essay_count=0,
            quiz_category_id="quiz-1", course_id="course-1",
            area="internal", group="grpBB", materials=self.materials,
        )
        self.assertTrue(plan["required"])
        self.assertEqual(plan["scoreGap"], 15)
        self.assertEqual([item["id"] for item in plan["reviewMaterials"]], ["sop-1", "guide-1"])
        self.assertEqual(plan["reviewMaterials"][0]["currentVersion"], 3)

    def test_passed_exam_has_no_remediation(self):
        plan = remediation.build_plan(
            score=88, passing_score=80, essay_count=0,
            quiz_category_id="quiz-1", course_id="course-1",
            area="internal", group="grpBB", materials=self.materials,
        )
        self.assertFalse(plan["required"])
        self.assertEqual(plan["reason"], "passed")
        self.assertEqual(plan["reviewMaterials"], [])

    def test_essay_exam_waits_for_final_review(self):
        plan = remediation.build_plan(
            score=20, passing_score=80, essay_count=1,
            quiz_category_id="quiz-1", course_id="course-1",
            area="internal", group="grpBB", materials=self.materials,
        )
        self.assertFalse(plan["required"])
        self.assertTrue(plan["pendingReview"])
        self.assertEqual(plan["reason"], "pending_review")

    def test_unlinked_exam_uses_same_category_only(self):
        plan = remediation.build_plan(
            score=50, passing_score=80, essay_count=0,
            quiz_category_id="quiz-1", course_id="",
            area="internal", group="grpBB", materials=self.materials,
        )
        self.assertEqual([item["id"] for item in plan["reviewMaterials"]], ["sop-1"])


if __name__ == "__main__":
    unittest.main()
