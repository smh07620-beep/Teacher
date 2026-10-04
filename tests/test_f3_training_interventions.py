import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.common.errors import ApiError
from teacher_app.learning import intervention_repository, intervention_service
from teacher_app.maintenance.training_intervention_migration import training_interventions_114


class F3TrainingInterventionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=str(Path(self.tmp.name)/"interventions.sqlite")

        def connect():
            conn=sqlite3.connect(self.db)
            conn.row_factory=sqlite3.Row
            conn.isolation_level=None
            return conn,"sqlite"

        self.connect=connect
        conn,kind=connect()
        training_interventions_114(conn,kind)
        conn.close()
        self.patch=patch("teacher_app.common.db.get_connection",side_effect=connect)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.actor={
            "username":"leader","role":"group_leader","roles":["group_leader"],
            "preferredArea":"internal","preferredGroup":"grpBio",
        }
        self.row={
            "username":"student","name":"Student","empId":"E1",
            "area":"internal","group":"grpBio","courseId":"c1","courseTitle":"Course",
            "status":"remediation","qualificationStatus":"remediation",
            "materialsCompleted":1,"materialsTotal":1,"materialsComplete":True,
            "requiredMaterialIds":["m1"],"retrainingMaterialIds":[],
            "retrainingRequired":False,"examRequired":True,"examPassed":False,
            "examStatus":"remediation","completed":False,"dueAt":"",
            "evidence":{"exam":{"quizCategoryId":"e1","score":60,"passingScore":80}},
        }

    def test_create_is_idempotent_per_active_learner_course(self):
        matrix={"rows":[self.row],"scope":{"area":"internal","group":"grpBio"}}
        material={"id":"m1","courseId":"c1","area":"internal","group":"grpBio","active":True,"title":"SOP"}
        with patch.object(intervention_service.compliance_service,"build_matrix",return_value=matrix), \
             patch.object(intervention_service.material_repository,"list_uploaded_materials",return_value=[material]), \
             patch.object(intervention_service.audit,"record_event",return_value=None):
            first=intervention_service.create_or_refresh(self.actor,{"username":"student","courseId":"c1"})
            second=intervention_service.create_or_refresh(self.actor,{"username":"student","courseId":"c1","internalNote":"follow"})
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        rows=intervention_repository.list_interventions(username="student")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["kind"],"remediation")
        self.assertEqual(rows[0]["internalNote"],"follow")

    def test_resolution_fails_closed_while_evidence_still_requires_intervention(self):
        case=intervention_repository.insert_intervention({
            "id":"INT-1","username":"student","emp_id":"E1","course_id":"c1",
            "source_status":"remediation","kind":"remediation","status":"in_progress",
            "learner_message":"","internal_note":"","plan_json":"{}",
            "created_by":"leader","created_at":"2026-10-04T00:00:00+00:00",
            "updated_by":"leader","updated_at":"2026-10-04T00:00:00+00:00",
            "resolved_at":"","resolution_json":"{}",
        })
        with patch.object(intervention_service.compliance_service,"build_matrix",return_value={"rows":[self.row]}), \
             patch.object(intervention_service.material_repository,"list_uploaded_materials",return_value=[]):
            with self.assertRaises(ApiError) as caught:
                intervention_service.update_case(self.actor,case["id"],{"status":"resolved"})
        self.assertEqual(caught.exception.code,"INTERVENTION_STILL_REQUIRED")

    def test_resolution_requires_canonical_evidence_to_clear(self):
        case=intervention_repository.insert_intervention({
            "id":"INT-2","username":"student","emp_id":"E1","course_id":"c1",
            "source_status":"overdue","kind":"overdue","status":"in_progress",
            "learner_message":"","internal_note":"","plan_json":"{}",
            "created_by":"leader","created_at":"2026-10-04T00:00:00+00:00",
            "updated_by":"leader","updated_at":"2026-10-04T00:00:00+00:00",
            "resolved_at":"","resolution_json":"{}",
        })
        complete={**self.row,"status":"complete","qualificationStatus":"passed","completed":True,"examPassed":True}
        with patch.object(intervention_service.compliance_service,"build_matrix",return_value={"rows":[complete]}), \
             patch.object(intervention_service.audit,"record_event",return_value=None):
            result=intervention_service.update_case(self.actor,case["id"],{"status":"resolved"})
        self.assertEqual(result["intervention"]["status"],"resolved")
        self.assertTrue(result["intervention"]["resolvedAt"])
        self.assertTrue(result["intervention"]["resolution"]["completed"])

    def test_learner_projection_hides_internal_notes(self):
        intervention_repository.insert_intervention({
            "id":"INT-3","username":"student","emp_id":"E1","course_id":"c1",
            "source_status":"retraining","kind":"retraining","status":"open",
            "learner_message":"請重讀","internal_note":"manager-only","plan_json":json.dumps({"type":"retraining"}),
            "created_by":"leader","created_at":"2026-10-04T00:00:00+00:00",
            "updated_by":"leader","updated_at":"2026-10-04T00:00:00+00:00",
            "resolved_at":"","resolution_json":"{}",
        })
        with patch.object(intervention_service.course_repository,"get_course",return_value={"id":"c1","title":"Course"}):
            data=intervention_service.mine({"username":"student"})
        self.assertEqual(data["activeCount"],1)
        self.assertNotIn("internalNote",data["items"][0])
        self.assertNotIn("createdBy",data["items"][0])


if __name__=="__main__":
    unittest.main()
