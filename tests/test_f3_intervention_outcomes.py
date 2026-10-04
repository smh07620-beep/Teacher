import datetime as dt
import unittest
from unittest.mock import patch

from teacher_app.learning import intervention_service


ACTOR={
    "username":"leader","role":"group_leader","roles":["group_leader"],
    "preferredArea":"internal","preferredGroup":"grpBio",
}


class F3InterventionOutcomeTests(unittest.TestCase):
    def test_manager_summary_reports_evidence_ready_and_resolution_time(self):
        matrix={"scope":{"area":"internal","group":"grpBio"},"rows":[{
            "username":"student","courseId":"c1","status":"complete","completed":True,
            "materialsComplete":True,"examPassed":True,"certificateStatus":"current","certificateId":"CERT-1",
        }]}
        rows=[
            {
                "id":"I1","username":"student","courseId":"c1","kind":"remediation",
                "status":"in_progress","createdAt":"2026-10-01T00:00:00+00:00","resolvedAt":"",
            },
            {
                "id":"I2","username":"student","courseId":"c1","kind":"overdue",
                "status":"resolved","createdAt":"2026-10-01T00:00:00+00:00",
                "resolvedAt":"2026-10-02T12:00:00+00:00",
            },
        ]
        with patch.object(intervention_service.compliance_service,"build_matrix",return_value=matrix), \
             patch.object(intervention_service.intervention_repository,"list_interventions",return_value=rows):
            result=intervention_service.manager_list(ACTOR)
        self.assertEqual(result["summary"]["active"],1)
        self.assertEqual(result["summary"]["readyToResolve"],1)
        self.assertEqual(result["summary"]["resolved"],1)
        self.assertEqual(result["summary"]["averageResolutionHours"],36.0)
        self.assertEqual(result["items"][0]["currentEvidence"]["certificateStatus"],"current")

    def test_resolution_snapshot_keeps_certificate_evidence(self):
        current={
            "id":"I1","username":"student","courseId":"c1","kind":"remediation",
            "status":"in_progress","internalNote":"","learnerMessage":"","plan":{},
        }
        row={
            "username":"student","courseId":"c1","status":"complete","completed":True,
            "materialsComplete":True,"examPassed":True,
            "certificateStatus":"current","certificateId":"CERT-1","group":"grpBio",
        }
        captured={}
        def update(_id,**kwargs):
            captured.update(kwargs)
            return {**current,"status":"resolved","resolution":__import__("json").loads(kwargs["resolution_json"])}
        with patch.object(intervention_service.intervention_repository,"get_intervention",return_value=current), \
             patch.object(intervention_service,"_current_row",return_value=row), \
             patch.object(intervention_service.intervention_repository,"update_intervention",side_effect=update), \
             patch.object(intervention_service.audit,"record_event",return_value=None):
            result=intervention_service.update_case(ACTOR,"I1",{"status":"resolved"})
        resolution=result["intervention"]["resolution"]
        self.assertEqual(resolution["certificateStatus"],"current")
        self.assertEqual(resolution["certificateId"],"CERT-1")


if __name__=="__main__":
    unittest.main()
