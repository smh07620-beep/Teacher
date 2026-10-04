import unittest
from unittest.mock import patch

from teacher_app.materials import material_impact


class F6MaterialImpactTests(unittest.TestCase):
    def test_change_impact_finds_questions_exams_derivatives_and_learners(self):
        material={"id":"m1","title":"SOP","courseId":"c1","area":"internal","group":"grpBio","currentVersion":4}
        questions=[
            {"id":"q1","source_material_id":"m1","quiz_category_id":"e1","status":"reviewed","version":2,"question":"Q"},
            {"id":"q2","source_material_id":"other","quiz_category_id":"e2"},
        ]
        categories=[{"id":"e1","title":"Exam","active":True}]
        derivatives=[
            {"derivativeId":"p1","type":"presentation","materialVersion":4,"publishedAt":"now"},
            {"derivativeId":"v1","type":"video","materialVersion":3,"publishedAt":"old"},
        ]
        with patch.object(material_impact.material_repository,"get_material",return_value=material), \
             patch.object(material_impact.assessment_repository,"list_bank_questions",return_value=questions), \
             patch.object(material_impact.assessment_repository,"list_categories",return_value=categories), \
             patch.object(material_impact.ai_presentation_repository,"list_presentations",return_value=[{"id":"p1"}]), \
             patch.object(material_impact.derivative_repository,"list_for_material",return_value=derivatives), \
             patch.object(material_impact.assignment_service,"admin_list",return_value=[{"courseId":"c1"}]), \
             patch.object(material_impact,"_completed_learner_count",return_value=36):
            data=material_impact.analyze_material_change(
                {"username":"teacher"},
                "m1",
                proposed_version=5,
                requires_retraining=True,
            )
        self.assertEqual(data["summary"]["sourceQuestions"],1)
        self.assertEqual(data["summary"]["publishedExams"],1)
        self.assertEqual(data["summary"]["publishedPresentations"],1)
        self.assertEqual(data["summary"]["publishedVideos"],1)
        self.assertEqual(data["summary"]["completedLearners"],36)
        self.assertEqual(data["decision"]["retrainingAffectedLearners"],36)
        self.assertTrue(data["decision"]["historicEvidencePreserved"])
        self.assertTrue(all(item["willRequireReview"] for item in data["derivatives"]))


if __name__=="__main__":
    unittest.main()
