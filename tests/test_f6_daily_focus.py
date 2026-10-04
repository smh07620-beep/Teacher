import datetime as dt
import unittest
from unittest.mock import patch

from teacher_app.command_center import service


USER={
    "username":"leader","role":"group_leader","roles":["group_leader"],
    "preferredArea":"internal","preferredGroup":"grpBio",
}


class F6DailyFocusTests(unittest.TestCase):
    def test_teacher_intervention_is_projected_into_daily_queue(self):
        case={
            "id":"INT-1","username":"student","courseId":"c1","kind":"remediation",
            "status":"in_progress","learnerMessage":"請完成補強","resolutionEligible":False,
            "plan":{},
        }
        with patch.object(service,"has_permission",return_value=True), \
             patch.object(service.intervention_service,"manager_list",return_value={"items":[case]}), \
             patch.object(service.course_repository,"get_course",return_value={
                 "id":"c1","title":"Course","area":"internal","group":"grpBio","active":True
             }), \
             patch.object(service,"_visible_to_teacher",return_value=True):
            rows=service._teacher_intervention_items(USER)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["kind"],"intervention")
        self.assertEqual(rows[0]["actionLabel"],"查看介入追蹤")

    def test_resolution_eligible_intervention_becomes_closeout_action(self):
        case={
            "id":"INT-2","username":"student","courseId":"c1","kind":"retraining",
            "status":"in_progress","learnerMessage":"","resolutionEligible":True,
            "plan":{},
        }
        with patch.object(service,"has_permission",return_value=True), \
             patch.object(service.intervention_service,"manager_list",return_value={"items":[case]}), \
             patch.object(service.course_repository,"get_course",return_value={
                 "id":"c1","title":"Course","area":"internal","group":"grpBio","active":True
             }), \
             patch.object(service,"_visible_to_teacher",return_value=True):
            row=service._teacher_intervention_items(USER)[0]
        self.assertEqual(row["status"],"ready_to_resolve")
        self.assertEqual(row["actionLabel"],"前往結案")


if __name__=="__main__":
    unittest.main()
