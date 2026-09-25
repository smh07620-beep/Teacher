import unittest
from unittest.mock import patch

from teacher_app.common.errors import ApiError
from teacher_app.learning import assignment_service


COURSE = {
    "id": "course-bio",
    "area": "internal",
    "group": "grpBio",
}


class LearningAssignmentManagement83Tests(unittest.TestCase):
    def student(self):
        return {
            "username": "student.bio",
            "role": "student",
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }

    def leader(self):
        return {
            "username": "leader.bio",
            "role": "group_leader",
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }

    def admin(self):
        return {
            "username": "edu.admin",
            "role": "education_admin",
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }

    @patch("teacher_app.learning.assignment_service.course_repository.get_course", return_value=COURSE)
    def test_student_cannot_create_assignment(self, _course):
        with self.assertRaises(ApiError) as caught:
            assignment_service.create_assignment(
                self.student(),
                {"courseId": "course-bio", "assigneeType": "group", "assigneeKey": "grpBio"},
            )
        self.assertEqual(caught.exception.status, 403)

    @patch("teacher_app.learning.assignment_service.assignment_repository.list_assignments", return_value=[])
    @patch("teacher_app.learning.assignment_service.assignment_repository.insert_assignment")
    @patch("teacher_app.learning.assignment_service.course_repository.get_course", return_value=COURSE)
    def test_group_leader_can_assign_own_whole_group(self, _course, insert, _list):
        insert.side_effect = lambda values: {"id": values["id"], "group": values["group_key"]}
        result = assignment_service.create_assignment(
            self.leader(),
            {"courseId": "course-bio", "assigneeType": "group", "assigneeKey": "grpBio"},
        )
        self.assertEqual(result["group"], "grpBio")
        insert.assert_called_once()

    @patch("teacher_app.learning.assignment_service.course_repository.get_course", return_value=COURSE)
    def test_group_leader_cannot_assign_individual(self, _course):
        with self.assertRaises(ApiError) as caught:
            assignment_service.create_assignment(
                self.leader(),
                {"courseId": "course-bio", "assigneeType": "user", "assigneeKey": "student.bio"},
            )
        self.assertEqual(caught.exception.status, 403)

    @patch("teacher_app.learning.assignment_service.assignment_repository.list_assignments", return_value=[])
    @patch("teacher_app.learning.assignment_service.assignment_repository.insert_assignment")
    @patch("teacher_app.learning.assignment_service.course_repository.get_course", return_value=COURSE)
    def test_education_admin_can_assign_individual(self, _course, insert, _list):
        insert.side_effect = lambda values: {"id": values["id"], "assigneeType": values["assignee_type"]}
        result = assignment_service.create_assignment(
            self.admin(),
            {"courseId": "course-bio", "assigneeType": "user", "assigneeKey": "student.bio"},
        )
        self.assertEqual(result["assigneeType"], "user")

    @patch("teacher_app.learning.assignment_service.assignment_repository.list_assignments", return_value=[])
    def test_group_leader_cannot_list_other_group(self, _list):
        with self.assertRaises(ApiError) as caught:
            assignment_service.admin_list(self.leader(), area="internal", group="grpHema")
        self.assertEqual(caught.exception.status, 403)

    @patch("teacher_app.learning.assignment_service.assignment_repository.update_assignment")
    @patch("teacher_app.learning.assignment_service.assignment_repository.get_assignment")
    def test_group_leader_can_deactivate_own_group_assignment(self, get_assignment, update):
        get_assignment.return_value = {
            "id": "la-1",
            "courseId": "course-bio",
            "area": "internal",
            "group": "grpBio",
            "assigneeType": "group",
            "assigneeKey": "grpBio",
            "required": True,
            "dueAt": "",
            "active": True,
        }
        update.return_value = {**get_assignment.return_value, "active": False}
        result = assignment_service.update_assignment(self.leader(), "la-1", {"active": False})
        self.assertFalse(result["active"])

    @patch("teacher_app.learning.assignment_service.assignment_repository.update_assignment")
    @patch("teacher_app.learning.assignment_service.assignment_repository.list_assignments")
    @patch("teacher_app.learning.assignment_service.course_repository.get_course", return_value=COURSE)
    def test_recreating_cancelled_assignment_reactivates_existing_row(self, _course, list_rows, update):
        list_rows.return_value = [{
            "id": "la-old",
            "courseId": "course-bio",
            "area": "internal",
            "group": "grpBio",
            "assigneeType": "group",
            "assigneeKey": "grpBio",
            "required": True,
            "dueAt": "",
            "active": False,
        }]
        update.return_value = {**list_rows.return_value[0], "active": True}
        result = assignment_service.create_assignment(
            self.admin(),
            {"courseId": "course-bio", "assigneeType": "group", "assigneeKey": "grpBio"},
        )
        self.assertTrue(result["active"])
        update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
