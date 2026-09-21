from __future__ import annotations

import unittest
from unittest.mock import patch

from flask import Flask, g, jsonify

from teacher_app.auth import accounts
from teacher_app.common import scope, scope_filter
from teacher_app.common.errors import ApiError
from teacher_app.courses import service as course_service
from teacher_app.exams import records
from teacher_app.materials import service as material_service
from teacher_app.pgy import routes as pgy_routes


class StrictScopeWriteTests(unittest.TestCase):
    def test_legacy_projection_still_falls_back_but_write_validators_reject(self):
        self.assertEqual(scope.normalize_group("not-a-group"), scope.DEFAULT_GROUP)
        self.assertEqual(scope.normalize_area("not-an-area"), scope.DEFAULT_TRAINING_AREA)
        with self.assertRaises(ValueError):
            scope.validate_group("not-a-group")
        with self.assertRaises(ValueError):
            scope.validate_area("not-an-area")
        self.assertEqual(scope.validate_group("grpBio"), "grpBio")
        self.assertEqual(scope.validate_area("pgy"), "pgy")

    def test_account_create_rejects_invalid_group_before_persistence(self):
        with patch.object(accounts.repository, "create_user") as create_user:
            with self.assertRaisesRegex(ValueError, "組別格式不正確"):
                accounts.create_account(
                    {
                        "username": "scope-user",
                        "password": "pass",
                        "name": "Scope User",
                        "empId": "E1",
                        "preferredArea": "internal",
                        "preferredGroup": "typo-group",
                    }
                )
        create_user.assert_not_called()

    def test_course_create_rejects_invalid_area_before_persistence(self):
        with patch.object(course_service.repository, "create_course") as create_course:
            with self.assertRaises(ApiError) as raised:
                course_service.create_course(
                    None,
                    {"title": "CI", "group": "grpBio", "area": "typo-area"},
                )
        self.assertEqual(raised.exception.status, 400)
        self.assertEqual(raised.exception.code, "COURSE_SCOPE_INVALID")
        create_course.assert_not_called()

    def test_material_update_rejects_invalid_group_before_update(self):
        material = {
            "id": "m1",
            "title": "Material",
            "desc": "",
            "group": "grpBio",
            "area": "internal",
            "materialType": "standard",
            "active": True,
            "category": "",
            "courseId": "",
            "atlasMeta": {},
        }
        with patch.object(material_service.repository, "get_material", return_value=material), patch.object(
            material_service.repository, "update_material_metadata"
        ) as update:
            with self.assertRaises(ApiError) as raised:
                material_service.update_material("m1", {"group": "grpTypo"})
        self.assertEqual(raised.exception.status, 400)
        self.assertEqual(raised.exception.code, "MATERIAL_SCOPE_INVALID")
        update.assert_not_called()

    def test_exam_record_rejects_invalid_scope_before_database_write(self):
        user = {"name": "Learner", "empId": "E2"}
        payload = {
            "id": "record-1",
            "role": "student",
            "quizTitle": "Quiz",
            "score": 80,
            "status": "合格",
            "groupKey": "grpTypo",
            "trainingArea": "internal",
            "answersDetail": [],
        }
        with patch.object(records.common_db, "transaction") as transaction:
            with self.assertRaises(records.RecordError) as raised:
                records.create_record(user, payload)
        self.assertEqual(raised.exception.status, 400)
        transaction.assert_not_called()

    def test_canonical_permission_guard_rejects_invalid_write_scope_for_system_admin(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="scope-test")

        @app.before_request
        def bind_user():
            g.teacher_user = {
                "username": "admin",
                "role": "system_admin",
                "roles": ["system_admin"],
                "preferredGroup": "grpBio",
            }

        @app.post("/probe")
        def probe():
            denied = scope_filter.require_permission(app, "material.manage")
            if denied:
                return denied
            return jsonify({"ok": True})

        response = app.test_client().post(
            "/probe",
            json={"group": "grpTypo", "area": "internal"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.get_json()["invalidScope"])

    def test_pgy_assignment_write_boundary_rejects_invalid_scope(self):
        with self.assertRaises(ApiError) as raised:
            pgy_routes._validate_assignment_scope({"group": "grpTypo", "area": "pgy"})
        self.assertEqual(raised.exception.status, 400)
        self.assertEqual(raised.exception.code, "INVALID_SCOPE")


if __name__ == "__main__":
    unittest.main()
