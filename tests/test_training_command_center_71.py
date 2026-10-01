"""Teacher 7.1 M1 Training Command Center regressions."""
import datetime as dt
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

from teacher_app.command_center import service
from teacher_app.command_center.routes import register_training_command_center


ROOT = Path(__file__).parents[1]
NOW = dt.datetime(2026, 9, 16, 12, 0, tzinfo=dt.timezone.utc)


def assignment(status, *, assignment_id="a1", due_at="2026-09-17T12:00:00+00:00"):
    return {
        "id": assignment_id,
        "title": f"PGY {status}",
        "status": status,
        "group": "grpHema",
        "dueAt": due_at,
    }


class TrainingCommandCenterServiceTests(unittest.TestCase):
    def summary_for(self, role, rows, *, pgy=True):
        user = {
            "username": f"{role}-user",
            "role": role,
            "preferredGroup": "grpHema",
            "pgyLearner": pgy,
        }
        with patch("teacher_app.command_center.service.pgy_service.list_assignments", return_value=rows):
            return service.build_summary(user, now=NOW)

    def test_pgy_student_gets_assigned_work(self):
        data = self.summary_for("student", [assignment("assigned"), assignment("submitted", assignment_id="a2")])
        self.assertEqual([item["id"] for item in data["items"]], ["a1"])
        self.assertEqual(data["items"][0]["action"], "submit")
        self.assertEqual(data["items"][0]["persona"], "learner")
        self.assertEqual(data["scope"], ["online", "pgy"])
        self.assertTrue(data["pgyLearner"])
        self.assertEqual(data["audience"], "pgy")

    def test_online_student_never_receives_pgy_tasks(self):
        user = {"username": "online", "role": "student", "pgyLearner": False}
        with patch("teacher_app.command_center.service.pgy_service.list_assignments") as listing:
            data = service.build_summary(user, now=NOW)
        listing.assert_not_called()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["scope"], ["online"])
        self.assertFalse(data["pgyLearner"])
        self.assertEqual(data["audience"], "online")

    def test_learner_queue_converges_course_material_retraining_and_exam(self):
        user = {
            "username": "student-1",
            "role": "student",
            "roles": ["student"],
            "empId": "E001",
            "name": "學員甲",
            "pgyLearner": False,
        }
        dashboard = {
            "pendingCourses": [
                {"id": "c1", "assignmentId": "a1", "title": "生化必修", "area": "internal", "group": "grpBio", "dueAt": "2026-09-15T12:00:00+00:00", "overdue": True, "materialsCompleted": 1, "materialsTotal": 3, "examRequired": True, "examPassed": False},
            ],
            "pendingMaterials": [
                {"id": "m1", "title": "一般教材", "area": "internal", "group": "grpBio", "courseId": "c1", "retrainingRequired": False},
                {"id": "m2", "title": "重大改版 SOP", "area": "internal", "group": "grpBio", "courseId": "c1", "retrainingRequired": True},
                {"id": "m3", "title": "獨立教材", "area": "internal", "group": "grpBio", "courseId": "", "retrainingRequired": False},
            ],
            "pendingExams": [
                {"id": "q1", "title": "課程考核", "area": "internal", "group": "grpBio", "courseId": "c1", "passingScore": 80},
                {"id": "q2", "title": "獨立補測", "area": "internal", "group": "grpBio", "courseId": "", "passingScore": 80, "remediationRequired": True, "remediation": {"reviewMaterialCount": 2}},
            ],
        }
        with patch.object(service.audience, "current_profile", return_value={"audience": "online", "pgyLearner": False}), \
             patch.object(service.dashboard_service, "dashboard_summary", return_value=dashboard):
            data = service.build_summary(user, now=NOW)

        learner = [item for item in data["items"] if item.get("persona") == "learner"]
        self.assertEqual(data["counts"]["learner"], 4)
        self.assertEqual({item["kind"] for item in learner}, {"course", "retraining", "material", "exam"})
        self.assertNotIn("m1", {item["resourceId"] for item in learner})
        self.assertNotIn("q1", {item["resourceId"] for item in learner})
        self.assertTrue(next(item for item in learner if item["kind"] == "course")["overdue"])
        remediation = next(item for item in learner if item["resourceId"] == "q2")
        self.assertEqual(remediation["statusLabel"], "補強再測")

    def test_pgy_professional_roles_keep_existing_stage_mapping(self):
        cases = (
            ("clinical_teacher", "submitted", "teacher_sign"),
            ("group_leader", "teacher_signed", "group_countersign"),
            ("education_admin", "group_countersigned", "finalize"),
        )
        for role, status, action in cases:
            with self.subTest(role=role):
                data = self.summary_for(role, [assignment(status)])
                self.assertEqual(len(data["items"]), 1)
                self.assertEqual(data["items"][0]["action"], action)
                self.assertEqual(data["items"][0]["persona"], "teacher")

    def test_system_admin_and_auditor_do_not_gain_clinical_signing_tasks(self):
        for role in ("system_admin", "auditor"):
            with self.subTest(role=role), patch(
                "teacher_app.command_center.service.pgy_service.list_assignments"
            ) as listing:
                data = service.build_summary({"username": role, "role": role, "pgyLearner": False}, now=NOW)
                self.assertEqual(data["items"], [])
                self.assertEqual(data["counts"]["total"], 0)
                self.assertEqual(data["counts"]["learner"], 0)
                self.assertEqual(data["counts"]["teacher"], 0)
                self.assertEqual(data["counts"]["pgy"], 0)
                listing.assert_not_called()

    def test_overdue_tasks_are_counted_and_sorted_first(self):
        rows = [
            assignment("assigned", assignment_id="future", due_at="2026-09-18T12:00:00+00:00"),
            assignment("assigned", assignment_id="late", due_at="2026-09-15T12:00:00+00:00"),
        ]
        data = self.summary_for("student", rows)
        self.assertEqual([item["id"] for item in data["items"]], ["late", "future"])
        self.assertEqual(data["counts"]["overdue"], 1)
        self.assertTrue(data["items"][0]["overdue"])


class TrainingCommandCenterRouteTests(unittest.TestCase):
    def make_client(self, user):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")

        @app.before_request
        def bind_actor():
            g.teacher_user = user

        register_training_command_center(app)
        return app.test_client()

    def test_route_is_read_only_and_returns_summary(self):
        expected = {"role": "student", "audience": "online", "pgyLearner": False, "scope": ["online"], "counts": {"total": 0, "overdue": 0, "pgy": 0, "learner": 0, "teacher": 0}, "items": []}
        client = self.make_client({"username": "s", "role": "student", "pgyLearner": False})
        with patch("teacher_app.command_center.routes.service.build_summary", return_value=expected):
            response = client.get("/api/training-command-center")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), expected)
        self.assertEqual(client.post("/api/training-command-center").status_code, 405)

    def test_route_requires_login(self):
        client = self.make_client(None)
        response = client.get("/api/training-command-center")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.get_json()["loginRequired"])


class TrainingCommandCenterFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = ROOT.joinpath("static", "training-command-center-71.js").read_text(encoding="utf-8")
        cls.portal_todo = ROOT.joinpath("static", "learner-todo-convergence-1025.js").read_text(encoding="utf-8")
        cls.frontend = ROOT.joinpath("teacher_app", "frontend", "assets.py").read_text(encoding="utf-8")
        cls.entrypoint = ROOT.joinpath("teacher_app", "factory.py").read_text(encoding="utf-8")
        cls.matrix = ROOT.joinpath("RC_FEATURE_UI_COVERAGE_MATRIX.md").read_text(encoding="utf-8")

    def test_ui_is_compact_read_only_and_uses_single_command_source(self):
        self.assertIn("📌 我的待辦", self.ui)
        self.assertIn("getElementById('course-overview')", self.ui)
        self.assertIn("/api/training-command-center/profile", self.ui)
        self.assertIn("/api/training-command-center", self.ui)
        self.assertNotIn("/api/dashboard/me?", self.ui)
        self.assertIn("item?.persona === 'learner'", self.ui)
        self.assertIn("switchLearningModule('assessment')", self.ui)
        for mutation in ("method: 'POST'", "method: 'PATCH'", "method: 'DELETE'"):
            self.assertNotIn(mutation, self.ui)

    def test_portal_todo_overrides_count_and_rows_from_same_projection(self):
        self.assertIn("/api/training-command-center", self.portal_todo)
        self.assertIn("v681-home-todo-count", self.portal_todo)
        self.assertIn("v571-pending-exams", self.portal_todo)
        self.assertIn("item?.persona==='learner'", self.portal_todo)
        self.assertIn("learnerTodoSource='training-command-center'", self.portal_todo)
        self.assertNotIn("X-Admin-Key", self.portal_todo)
        self.assertNotIn("getAdminKey", self.portal_todo)

    def test_assets_are_composed_with_fresh_cache_key(self):
        self.assertIn("register_training_command_center", self.entrypoint)
        self.assertIn("register_training_audience_71", self.entrypoint)
        self.assertIn('"/training-command-center-71.js"', self.frontend)
        self.assertIn('"/learner-todo-convergence-1025.js"', self.frontend)
        self.assertLess(
            self.frontend.index('"/workspace-shell-70.js"'),
            self.frontend.index('"/training-command-center-71.js"'),
        )

    def test_rc_matrix_records_71_m1(self):
        self.assertIn("Training Command Center / 我的待辦 (7.1 M1)", self.matrix)
        self.assertIn("pgy_learner", self.matrix)
        self.assertIn("/api/dashboard/me", self.matrix)


if __name__ == "__main__":
    unittest.main()
