import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

from teacher_app.assessments import question_bank_routes
from teacher_app.courses import bundle_followup_routes, bundle_routes


ROOT = Path(__file__).resolve().parents[1]


class BaseFreeRouteSliceTests(unittest.TestCase):
    def test_allowed_route_modules_have_no_direct_base_attribute_access(self):
        for relative in (
            "teacher_app/courses/bundle_routes.py",
            "teacher_app/courses/bundle_followup_routes.py",
            "teacher_app/assessments/question_bank_routes.py",
        ):
            source = ROOT.joinpath(relative).read_text(encoding="utf-8")
            self.assertNotIn("base.", source, relative)

    def test_question_bank_exposes_explicit_runtime_question_dependency(self):
        app = Flask(__name__)
        sentinel = object()
        captured = []

        with patch(
            "teacher_app.assessments.runtime_question_routes.register_runtime_question_routes",
            side_effect=lambda owner, *, runtime: captured.append((owner, runtime)),
        ):
            question_bank_routes.register_question_bank(
                app,
                runtime_question_runtime=sentinel,
            )

        self.assertEqual(captured, [(app, sentinel)])
        self.assertIn("create_draft", app.view_functions)

    def test_bundle_registrars_accept_flask_app_without_base_container(self):
        bundle_app = Flask(__name__ + "-bundle")
        bundle_routes.register_course_bundle_72(bundle_app)
        self.assertIn("course_bundle_create_72", bundle_app.view_functions)

        followup_app = Flask(__name__ + "-followup")

        @followup_app.post("/api/material-jobs/upload", endpoint="api_enqueue_material_job")
        def upload():
            return {"ok": True}

        @followup_app.patch("/api/slides/<slide_id>", endpoint="api_update_slide")
        def link(slide_id):
            return {"id": slide_id}

        original_upload = followup_app.view_functions["api_enqueue_material_job"]
        original_link = followup_app.view_functions["api_update_slide"]
        bundle_followup_routes.register_course_bundle_followup_73(followup_app)
        self.assertIsNot(original_upload, followup_app.view_functions["api_enqueue_material_job"])
        self.assertIsNot(original_link, followup_app.view_functions["api_update_slide"])

    def test_question_bank_scope_guard_uses_request_bound_actor(self):
        app = Flask(__name__ + "-question-scope")
        actor = {
            "username": "teacher-1",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredGroup": "grpBio",
        }

        @app.before_request
        def bind_actor():
            g.teacher_user = actor

        with patch(
            "teacher_app.assessments.runtime_question_routes.register_runtime_question_routes"
        ), patch.object(
            question_bank_routes.scope_filter.assessment_repository,
            "get_category",
            return_value={"id": "cat-1", "group": "grpHema"},
        ), patch.object(
            question_bank_routes.bank_service,
            "create_draft",
        ) as create:
            question_bank_routes.register_question_bank(app, runtime_question_runtime=object())
            response = app.test_client().post(
                "/api/question-bank/drafts",
                json={"quizCategoryId": "cat-1", "question": "blocked"},
            )

        self.assertEqual(response.status_code, 403)
        create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
