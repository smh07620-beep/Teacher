import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from teacher_app.exams import record_routes


class ExamRecordReaderScopeTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.user = None
        self.owner = SimpleNamespace(app=self.app, _current_user=lambda: self.user)
        record_routes.register_record_routes(self.owner)
        self.client = self.app.test_client()
        self.rows = [
            {"id": "assigned", "empId": "S001", "reviewStatus": "pending", "groupKey": "grpBio"},
            {"id": "other", "empId": "S002", "reviewStatus": "pending", "groupKey": "grpBio"},
        ]

    def test_anonymous_record_list_is_rejected(self):
        response = self.client.get("/api/records")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.get_json()["loginRequired"])

    def test_clinical_teacher_receives_only_resource_scoped_records(self):
        self.user = {
            "username": "teacher1",
            "name": "王老師",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredGroup": "grpBio",
        }
        with patch.object(record_routes.records, "list_records", return_value=self.rows), \
             patch.object(
                 record_routes.records,
                 "can_review_record",
                 side_effect=lambda user, row: row["id"] == "assigned",
             ) as scoped:
            response = self.client.get("/api/records")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.get_json()], ["assigned"])
        self.assertEqual(scoped.call_count, 2)
        for call in scoped.call_args_list:
            self.assertEqual(call.args[0]["username"], "teacher1")

    def test_system_admin_keeps_full_read_overview_without_clinical_review_power(self):
        self.user = {
            "username": "sysadmin",
            "name": "系統管理員",
            "role": "system_admin",
            "roles": ["system_admin"],
        }
        with patch.object(record_routes.records, "list_records", return_value=self.rows), \
             patch.object(record_routes.records, "can_review_record") as scoped:
            response = self.client.get("/api/records")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.get_json()], ["assigned", "other"])
        scoped.assert_not_called()

        with patch.object(record_routes.records, "review_record") as review:
            denied = self.client.patch(
                "/api/records/assigned/review",
                json={"essayScores": {"0": 100}},
            )
        self.assertEqual(denied.status_code, 403)
        review.assert_not_called()

    def test_student_cannot_list_records(self):
        self.user = {
            "username": "student1",
            "name": "學員",
            "role": "student",
            "roles": ["student"],
        }
        with patch.object(record_routes.records, "list_records") as listing:
            response = self.client.get("/api/records")
        self.assertEqual(response.status_code, 403)
        listing.assert_not_called()

    def test_clinical_teacher_cannot_clear_record_history(self):
        self.user = {
            "username": "teacher1",
            "name": "王老師",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
        }
        with patch.object(record_routes.records, "clear_records") as clear:
            response = self.client.delete("/api/records")
        self.assertEqual(response.status_code, 403)
        clear.assert_not_called()


if __name__ == "__main__":
    unittest.main()
