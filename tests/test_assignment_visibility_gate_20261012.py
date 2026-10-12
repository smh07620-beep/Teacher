"""2026-10-12: students only see courses assigned to them; unassigned = nobody (but staff)."""
import unittest
from unittest.mock import patch

from teacher_app.common import content_audience
from teacher_app.learning import access

COURSE_ITEM = {"id": "m1", "courseId": "c1", "area": "internal", "group": "grpBio", "active": True}
LOOSE_ITEM = {"id": "m9", "area": "internal", "group": "grpBio", "active": True}
COURSE_REC = {"id": "c1", "area": "internal", "group": "grpBio", "lifecycleStatus": "published"}
META = {"courseId": "c1", "ownerGroup": "grpBio", "audienceScope": "group_only", "audienceGroups": []}


def person(role, group="grpBio", name="u1"):
    return {"username": name, "role": role, "roles": [role], "preferredArea": "internal", "preferredGroup": group}


def assigned(rows):
    return patch("teacher_app.learning.assignment_repository.list_for_user", return_value=[{"courseId": r} for r in rows])


class AssignmentGateTests(unittest.TestCase):
    def test_unassigned_student_in_same_group_sees_nothing_of_the_course(self):
        with assigned([]):
            s = person("student")
            self.assertFalse(access.can_access_learning_item(s, COURSE_ITEM))
            self.assertFalse(access.can_access_learning_item(s, COURSE_REC))
            self.assertFalse(content_audience.visible_to_user(s, META))

    def test_assigned_student_sees_only_that_course(self):
        with assigned(["c1"]):
            s = person("student")
            self.assertTrue(access.can_access_learning_item(s, COURSE_ITEM))
            self.assertTrue(content_audience.visible_to_user(s, META))
            self.assertFalse(access.can_access_learning_item(s, {**COURSE_ITEM, "courseId": "c2"}))

    def test_legacy_learner_role_is_gated_too(self):
        with assigned([]):
            self.assertFalse(access.can_access_learning_item(person("learner"), COURSE_ITEM))

    def test_staff_are_never_gated(self):
        with assigned([]):
            for role in ("clinical_teacher", "group_leader", "education_admin", "system_admin", "auditor"):
                self.assertTrue(access.can_access_learning_item(person(role), COURSE_ITEM), role)
                self.assertTrue(content_audience.visible_to_user(person(role), META), role)

    def test_student_who_is_also_teacher_is_not_gated(self):
        both = {**person("student"), "roles": ["student", "clinical_teacher"]}
        with assigned([]):
            self.assertTrue(access.can_access_learning_item(both, COURSE_ITEM))

    def test_items_without_a_course_keep_group_visibility(self):
        with assigned([]):
            self.assertTrue(access.can_access_learning_item(person("student"), LOOSE_ITEM))
            self.assertFalse(access.can_access_learning_item(person("student", "grpHema"), LOOSE_ITEM))

    def test_assignment_lookup_failure_fails_closed(self):
        with patch("teacher_app.learning.assignment_repository.list_for_user", side_effect=RuntimeError("db down")):
            self.assertFalse(access.can_access_learning_item(person("student"), COURSE_ITEM))

    def test_assignment_is_per_person(self):
        def rows(*, username, area, group):
            return [{"courseId": "c1"}] if username == "u1" else []
        with patch("teacher_app.learning.assignment_repository.list_for_user", side_effect=rows):
            self.assertTrue(access.can_access_learning_item(person("student", name="u1"), COURSE_ITEM))
            self.assertFalse(access.can_access_learning_item(person("student", name="u2"), COURSE_ITEM))


if __name__ == "__main__":
    unittest.main()


class LearnerViewTests(unittest.TestCase):
    """Reading area (?view=learner) treats staff like learners; management pages do not."""

    def test_staff_in_reading_area_only_see_assigned_courses(self):
        with assigned([]):
            for role in ("clinical_teacher", "group_leader", "education_admin", "system_admin"):
                u = person(role)
                self.assertFalse(access.can_access_learning_item(u, COURSE_ITEM, learner_view=True), role)
                self.assertTrue(access.can_access_learning_item(u, COURSE_ITEM, learner_view=False), role)
        with assigned(["c1"]):
            self.assertTrue(access.can_access_learning_item(person("clinical_teacher"), COURSE_ITEM, learner_view=True))

    def test_request_flag_switches_the_view(self):
        from flask import Flask
        app = Flask(__name__)
        teacher = person("clinical_teacher")
        with assigned([]):
            with app.test_request_context("/api/courses?view=learner"):
                self.assertTrue(access.learner_view_requested())
                self.assertFalse(access.can_access_learning_item(teacher, COURSE_ITEM))
                self.assertFalse(content_audience.visible_to_user(teacher, META))
            with app.test_request_context("/api/courses"):
                self.assertFalse(access.learner_view_requested())
                self.assertTrue(access.can_access_learning_item(teacher, COURSE_ITEM))
                self.assertTrue(content_audience.visible_to_user(teacher, META))

    def test_course_list_filter_for_managers_only_narrows_in_reading_area(self):
        from flask import Flask
        from teacher_app.courses.visibility import filter_courses_for_user
        app = Flask(__name__)
        admin = person("education_admin")
        courses = [{"id": "c1", "group": "grpBio", "area": "internal"}, {"id": "c2", "group": "grpBio", "area": "internal"}]
        with assigned(["c1"]):
            with app.test_request_context("/api/courses?view=learner"):
                self.assertEqual([c["id"] for c in filter_courses_for_user(admin, courses)], ["c1"])
            with app.test_request_context("/api/courses"):
                self.assertEqual([c["id"] for c in filter_courses_for_user(admin, courses)], ["c1", "c2"])

    def test_learner_page_sends_the_flag_and_admin_pages_do_not(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / "static"
        learner = (root / "system-learner.js").read_text(encoding="utf-8")
        self.assertEqual(learner.count("view=learner"), 3)
        for name in ("admin-course-material.js", "system-exam.js", "admin-question-bank.js"):
            self.assertNotIn("view=learner", (root / name).read_text(encoding="utf-8"), name)


class ExamStartGateTests(unittest.TestCase):
    def test_student_cannot_start_exam_of_unassigned_course(self):
        from teacher_app.common.errors import ApiError
        from teacher_app.exams import service as exams_service

        category = {"id": "cat1", "active": True, "courseId": "c1", "group": "grpBio", "area": "internal"}
        student = {**person("student"), "empId": "E1"}
        with assigned([]), \
             patch.object(exams_service, "assert_exam_open"), \
             patch("teacher_app.assessments.repository.get_category_full", return_value=category), \
             patch("teacher_app.assessments.assignees.assert_can_take"):
            with self.assertRaises(ApiError) as ctx:
                exams_service.start_attempt(student, {"quizCategoryId": "cat1"})
        self.assertEqual(ctx.exception.status, 403)
