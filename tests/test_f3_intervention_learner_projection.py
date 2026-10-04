import datetime as dt
import unittest
from unittest.mock import patch

from teacher_app.command_center import service


NOW=dt.datetime(2026,10,4,12,0,tzinfo=dt.timezone.utc)
USER={"username":"student","role":"student","roles":["student"],"empId":"E1"}


class F3InterventionLearnerProjectionTests(unittest.TestCase):
    def _dashboard(self):
        return {
            "pendingCourses":[{
                "id":"c1","assignmentId":"a1","title":"Course","area":"internal","group":"grpBio",
                "dueAt":"","overdue":False,"materialsCompleted":1,"materialsTotal":1,
                "examRequired":True,"examPassed":False,"nextKind":"exam","resumeExamId":"e1",
            }],
            "pendingMaterials":[],
            "pendingExams":[],
        }

    def test_remediation_case_overrides_next_action_to_review_material(self):
        case={
            "id":"INT-1","courseId":"c1","kind":"remediation","status":"in_progress",
            "learnerMessage":"請先複習 SOP 再測",
            "plan":{"quizCategoryId":"e1","reviewMaterials":[{"id":"m1","title":"SOP"}]},
        }
        with patch.object(service.dashboard_service,"dashboard_summary",return_value=self._dashboard()), \
             patch.object(service.intervention_service,"mine",return_value={"items":[case]}):
            items=service._learner_action_items(USER,NOW)
        row=items[0]
        self.assertEqual(row["interventionId"],"INT-1")
        self.assertEqual(row["materialId"],"m1")
        self.assertEqual(row["target"],"materials")
        self.assertEqual(row["actionLabel"],"先完成補強教材")
        self.assertEqual(row["detail"],"請先複習 SOP 再測")

    def test_ready_for_retest_points_to_exact_exam(self):
        case={
            "id":"INT-2","courseId":"c1","kind":"remediation","status":"ready_for_retest",
            "learnerMessage":"可以再測",
            "plan":{"quizCategoryId":"e1","reviewMaterials":[{"id":"m1","title":"SOP"}]},
        }
        with patch.object(service.dashboard_service,"dashboard_summary",return_value=self._dashboard()), \
             patch.object(service.intervention_service,"mine",return_value={"items":[case]}):
            items=service._learner_action_items(USER,NOW)
        row=items[0]
        self.assertEqual(row["resourceId"],"e1")
        self.assertEqual(row["target"],"exam")
        self.assertEqual(row["actionLabel"],"進行再測")

    def test_intervention_failure_is_fail_soft_for_existing_learning_tasks(self):
        with patch.object(service.dashboard_service,"dashboard_summary",return_value=self._dashboard()), \
             patch.object(service.intervention_service,"mine",side_effect=RuntimeError("missing table")):
            items=service._learner_action_items(USER,NOW)
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]["courseId"],"c1")
        self.assertNotIn("interventionId",items[0])


if __name__=="__main__":
    unittest.main()
