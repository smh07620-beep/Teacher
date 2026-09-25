import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from teacher_app.learning import access as learning_access
from teacher_app.learning.assignment_routes import register_learning_assignment_routes
from teacher_app.frontend import assets


COURSE = {"id": "course-bio", "title": "Bio Core", "area": "internal", "group": "grpBio"}


def actor(role="clinical_teacher", group="grpBio"):
    return {
        "username": f"{role}.user", "name": role, "empId": "E1", "role": role,
        "preferredArea": "internal", "preferredGroup": group,
    }


class AssignmentRouteTests(unittest.TestCase):
    def make_client(self, user):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")
        owner = SimpleNamespace(app=app, _current_user=lambda: user)
        register_learning_assignment_routes(owner)
        return app.test_client()

    @patch("teacher_app.learning.assignment_routes.course_repository.get_course", return_value=COURSE)
    def test_student_cannot_manage_assignments(self, _course):
        response = self.make_client(actor("student")).get("/api/learning-assignments?courseId=course-bio")
        self.assertEqual(response.status_code, 403)

    @patch("teacher_app.learning.assignment_routes.auth_repository.list_users")
    @patch("teacher_app.learning.assignment_routes.course_repository.get_course", return_value=COURSE)
    def test_teacher_candidates_are_limited_to_own_course_group(self, _course, users):
        users.return_value = [
            {"username":"bio1","display_name":"Bio","emp_id":"B1","preferred_area":"internal","preferred_group":"grpBio","active":1},
            {"username":"micro1","display_name":"Micro","emp_id":"M1","preferred_area":"internal","preferred_group":"grpMicro","active":1},
        ]
        data = self.make_client(actor()).get("/api/learning-assignments/candidates?courseId=course-bio").get_json()
        self.assertEqual([u["username"] for u in data["users"]], ["bio1"])
        self.assertFalse(data["canAssignAll"])

    @patch("teacher_app.learning.assignment_routes.audit.record_event")
    @patch("teacher_app.learning.assignment_routes.assignment_service.create_assignment")
    @patch("teacher_app.learning.assignment_routes.auth_repository.find_user")
    @patch("teacher_app.learning.assignment_routes.course_repository.get_course", return_value=COURSE)
    def test_teacher_cannot_assign_cross_group_user(self, _course, find_user, create, audit):
        find_user.return_value = {"username":"micro1","active":1,"preferred_area":"internal","preferred_group":"grpMicro"}
        response = self.make_client(actor()).post("/api/learning-assignments", json={"courseId":"course-bio","assigneeType":"user","assigneeKey":"micro1"})
        self.assertEqual(response.status_code, 403)
        create.assert_not_called(); audit.assert_not_called()

    @patch("teacher_app.learning.assignment_routes.audit.record_event")
    @patch("teacher_app.learning.assignment_routes.assignment_service.create_assignment")
    @patch("teacher_app.learning.assignment_routes.course_repository.get_course", return_value=COURSE)
    def test_education_admin_can_create_all_assignment(self, _course, create, audit):
        create.return_value = {"id":"la-1","courseId":"course-bio","area":"internal","group":"grpBio","assigneeType":"all","assigneeKey":"*","required":True,"active":True}
        response = self.make_client(actor("education_admin")).post("/api/learning-assignments", json={"courseId":"course-bio","assigneeType":"all","assigneeKey":"*","required":True})
        self.assertEqual(response.status_code, 201)
        create.assert_called_once(); audit.assert_called_once()

    @patch("teacher_app.learning.assignment_routes.audit.record_event")
    @patch("teacher_app.learning.assignment_routes.assignment_service.deactivate_assignment")
    @patch("teacher_app.learning.assignment_routes.assignment_repository.get_assignment")
    @patch("teacher_app.learning.assignment_routes.course_repository.get_course", return_value=COURSE)
    def test_deactivate_is_soft_and_audited(self, _course, get_assignment, deactivate, audit):
        get_assignment.return_value = {"id":"la-1","courseId":"course-bio","area":"internal","group":"grpBio","active":True}
        deactivate.return_value = {**get_assignment.return_value, "active":False}
        response = self.make_client(actor()).delete("/api/learning-assignments/la-1")
        self.assertEqual(response.status_code, 200)
        deactivate.assert_called_once_with("la-1"); audit.assert_called_once()


class AssignmentAccessTests(unittest.TestCase):
    def test_explicit_cross_group_assignment_grants_only_assigned_course(self):
        user = actor("student")
        rows = [{"courseId":"foreign-course","area":"internal","group":"grpMicro","assigneeType":"user","assigneeKey":user["username"]}]
        with patch("teacher_app.learning.assignment_service.list_for_user", return_value=rows):
            self.assertTrue(learning_access.can_access_learning_item(user, {"id":"m1","courseId":"foreign-course","area":"internal","group":"grpMicro"}))
            self.assertFalse(learning_access.can_access_learning_item(user, {"id":"m2","courseId":"other-course","area":"internal","group":"grpMicro"}))
            self.assertTrue(learning_access.can_access_requested_scope(user, "internal", "grpMicro"))
            self.assertEqual(learning_access.assigned_courses_in_scope(user, "internal", "grpMicro"), {"foreign-course"})


class AssignmentFrontendContractTests(unittest.TestCase):
    def test_assignment_asset_is_canonical_system_asset(self):
        self.assertIn("/admin-learning-assignments.js", assets.ASSET_MANIFEST["system"]["body"])

    def test_assignment_ui_has_no_browser_secret_and_uses_management_api(self):
        source = open("static/admin-learning-assignments.js", encoding="utf-8").read()
        self.assertIn("/api/learning-assignments", source)
        self.assertIn("assigneeType", source)
        self.assertIn("required", source)
        self.assertIn("dueAt", source)
        self.assertNotIn("X-Admin-Key", source)
        self.assertNotIn("getAdminKey", source)


if __name__ == "__main__":
    unittest.main()
