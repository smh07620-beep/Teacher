import datetime as dt
import unittest
from unittest.mock import patch

from teacher_app.command_center import service


NOW=dt.datetime(2026,10,4,12,0,tzinfo=dt.timezone.utc)
USER={"username":"s1","name":"Learner","empId":"E1","role":"student","roles":["student"]}


class F2LearnerNextActionTests(unittest.TestCase):
    def test_course_action_resumes_exact_partial_material(self):
        dashboard={
            "pendingCourses":[{
                "id":"c1","assignmentId":"a1","title":"Course","area":"internal","group":"grpBio",
                "dueAt":"","overdue":False,"materialsCompleted":0,"materialsTotal":2,
                "examRequired":True,"examPassed":False,"nextKind":"material",
                "resumeMaterialId":"m2","resumeMaterialTitle":"SOP","resumeProgress":42,
            }],
            "pendingMaterials":[
                {"id":"m2","courseId":"c1","title":"SOP","area":"internal","group":"grpBio","progress":42}
            ],
            "pendingExams":[{"id":"e1","courseId":"c1","title":"Exam","area":"internal","group":"grpBio","passingScore":80}],
        }
        with patch.object(service.dashboard_service,"dashboard_summary",return_value=dashboard), \
             patch.object(service.audience,"current_profile",return_value={"audience":"online","pgyLearner":False}), \
             patch.object(service,"_teacher_action_items",return_value=[]):
            data=service.build_summary(USER,now=NOW)
        item=data["nextAction"]
        self.assertEqual(item["kind"],"course")
        self.assertEqual(item["materialId"],"m2")
        self.assertEqual(item["actionLabel"],"繼續閱讀 42%")
        self.assertEqual(item["target"],"materials")
        self.assertEqual(data["items"][0],item)

    def test_course_action_moves_to_exam_after_materials_done(self):
        dashboard={
            "pendingCourses":[{
                "id":"c1","assignmentId":"a1","title":"Course","area":"internal","group":"grpBio",
                "dueAt":"","overdue":False,"materialsCompleted":2,"materialsTotal":2,
                "examRequired":True,"examPassed":False,"nextKind":"exam","resumeExamId":"e1",
            }],
            "pendingMaterials":[],
            "pendingExams":[{"id":"e1","courseId":"c1","title":"Exam","area":"internal","group":"grpBio","passingScore":80}],
        }
        with patch.object(service.dashboard_service,"dashboard_summary",return_value=dashboard), \
             patch.object(service.audience,"current_profile",return_value={"audience":"online","pgyLearner":False}), \
             patch.object(service,"_teacher_action_items",return_value=[]):
            data=service.build_summary(USER,now=NOW)
        self.assertEqual(data["nextAction"]["resourceId"],"e1")
        self.assertEqual(data["nextAction"]["target"],"exam")
        self.assertEqual(data["nextAction"]["actionLabel"],"開始考核")


if __name__=="__main__":
    unittest.main()
