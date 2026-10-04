import unittest
from unittest.mock import patch

from teacher_app.command_center import course_tracking


class F2CourseTrackingTests(unittest.TestCase):
    def test_assignment_expansion_respects_user_group_and_area_all(self):
        accounts=[
            {"username":"a","area":"internal","group":"grpBio"},
            {"username":"b","area":"internal","group":"grpHema"},
            {"username":"c","area":"pgy","group":"grpBio"},
        ]
        self.assertEqual([r["username"] for r in course_tracking._expand_assignment({"assigneeType":"user","assigneeKey":"b"},accounts)],["b"])
        self.assertEqual([r["username"] for r in course_tracking._expand_assignment({"assigneeType":"group","area":"internal","group":"grpBio"},accounts)],["a"])
        self.assertEqual([r["username"] for r in course_tracking._expand_assignment({"assigneeType":"all","area":"internal"},accounts)],["a","b"])

    def test_projection_counts_actionable_course_states(self):
        user={"username":"admin","role":"education_admin","roles":["education_admin"],"permissions":["learning.assign"]}
        assignment={"courseId":"c1","area":"internal","group":"grpBio","assigneeType":"user","assigneeKey":"s1","dueAt":"2026-10-01T00:00:00+00:00","active":True}
        course={"id":"c1","title":"Course","area":"internal","group":"grpBio","active":True,"lifecycleStatus":"published"}
        learner={"username":"s1","name":"Learner","empId":"E1","area":"internal","group":"grpBio","active":True}
        material={"id":"m1","courseId":"c1","active":True,"version":1,"requiredCompletionVersion":1}
        with patch.object(course_tracking.assignment_service,"admin_list",return_value=[assignment]), \
             patch.object(course_tracking,"_account_rows",return_value=[learner]), \
             patch.object(course_tracking.course_repository,"get_course",return_value=course), \
             patch.object(course_tracking.material_repository,"list_uploaded_materials",return_value=[material]), \
             patch.object(course_tracking.assessment_repository,"list_categories",return_value=[]), \
             patch.object(course_tracking,"_progress_rows",return_value=[]), \
             patch.object(course_tracking,"_legacy_progress_rows",return_value=[]), \
             patch.object(course_tracking,"_exam_rows",return_value=[]), \
             patch.object(course_tracking,"has_permission",return_value=True):
            data=course_tracking.build_course_tracking(user)
        self.assertEqual(data["summary"]["assigned"],1)
        self.assertEqual(data["summary"]["notStarted"],1)
        self.assertEqual(data["summary"]["overdue"],1)
        self.assertEqual(data["courses"][0]["learners"][0]["status"],"notStarted")


if __name__=="__main__":
    unittest.main()
