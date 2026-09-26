import unittest
from unittest.mock import patch

from flask import Flask, g

from teacher_app.common.errors import register_error_handlers
from teacher_app.learning.compliance_routes import register_training_compliance_routes


class TrainingComplianceRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "test"

        @self.app.before_request
        def bind_user():
            g.teacher_user = {
                "username": "admin",
                "role": "education_admin",
                "roles": ["education_admin"],
            }

        register_training_compliance_routes(self.app)
        register_error_handlers(self.app)
        self.client = self.app.test_client()

    def test_route_forwards_filters(self):
        payload = {
            "scope": {},
            "filters": {},
            "summary": {"total": 0},
            "rows": [],
        }
        with patch(
            "teacher_app.learning.compliance_routes.compliance_service.build_matrix",
            return_value=payload,
        ) as build:
            response = self.client.get(
                "/api/training-compliance?area=internal&group=grpBio&status=overdue&courseId=c1"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["rows"], [])
        kwargs = build.call_args.kwargs
        self.assertEqual(kwargs["area"], "internal")
        self.assertEqual(kwargs["group"], "grpBio")
        self.assertEqual(kwargs["status"], "overdue")
        self.assertEqual(kwargs["course_id"], "c1")


if __name__ == "__main__":
    unittest.main()
