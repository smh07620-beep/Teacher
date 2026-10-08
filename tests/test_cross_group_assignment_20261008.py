"""Individual assignment from another group = explicit per-person grant for ONE course."""
import unittest
from unittest.mock import patch

from teacher_app.common import content_audience
from teacher_app.common.errors import ApiError
from teacher_app.courses import visibility
from teacher_app.learning import access, assignment_service

COURSE = {"id": "course-bio", "area": "internal", "group": "grpBio", "active": True, "lifecycleStatus": "published"}
HEMA_USER = {"username": "student.hema", "role": "student", "preferredArea": "internal", "preferredGroup": "grpHema"}
HEMA_ACCOUNT = {"username": "student.hema", "name": "血液學員", "empId": "10002", "active": True,
                "preferredArea": "internal", "preferredGroup": "grpHema"}
BIO_MATERIAL = {"id": "m1", "courseId": "course-bio", "area": "internal", "group": "grpBio", "active": True}
OTHER_MATERIAL = {"id": "m2", "courseId": "course-other", "area": "internal", "group": "grpBio", "active": True}


def _grants(ids):
    return patch("teacher_app.learning.assignment_repository.list_personal_course_ids", return_value=list(ids))


def _course(course=COURSE):
    return patch("teacher_app.courses.repository.get_course", return_value=course)


class PersonalGrantAccessTests(unittest.TestCase):
    def test_without_assignment_other_group_content_stays_hidden(self):
        with _grants([]):
            self.assertFalse(access.can_access_learning_item(HEMA_USER, BIO_MATERIAL))

    def test_assignment_opens_only_that_course(self):
        with _grants(["course-bio"]), _course():
            self.assertTrue(access.can_access_learning_item(HEMA_USER, BIO_MATERIAL))
            self.assertTrue(access.can_access_learning_item(HEMA_USER, COURSE))
            self.assertFalse(access.can_access_learning_item(HEMA_USER, OTHER_MATERIAL))

    def test_unpublished_or_inactive_course_grants_nothing(self):
        with _grants(["course-bio"]), _course({**COURSE, "lifecycleStatus": "draft"}):
            self.assertFalse(access.can_access_learning_item(HEMA_USER, BIO_MATERIAL))
        with _grants(["course-bio"]), _course({**COURSE, "active": False}):
            self.assertFalse(access.can_access_learning_item(HEMA_USER, BIO_MATERIAL))

    def test_grant_is_per_person(self):
        other = {**HEMA_USER, "username": "someone.else"}
        with patch("teacher_app.learning.assignment_repository.list_personal_course_ids",
                   side_effect=lambda username, area: ["course-bio"] if username == "student.hema" else []), _course():
            self.assertTrue(access.can_access_learning_item(HEMA_USER, BIO_MATERIAL))
            self.assertFalse(access.can_access_learning_item(other, BIO_MATERIAL))

    def test_material_and_exam_audience_projection_honours_grant(self):
        meta = {"courseId": "course-bio", "ownerGroup": "grpBio", "audienceScope": "group_only", "audienceGroups": []}
        with _grants([]):
            self.assertFalse(content_audience.visible_to_user(HEMA_USER, meta))
        with _grants(["course-bio"]), _course():
            self.assertTrue(content_audience.visible_to_user(HEMA_USER, meta))
            self.assertFalse(content_audience.visible_to_user(HEMA_USER, {**meta, "courseId": "course-other"}))


class VisibilityListTests(unittest.TestCase):
    def test_course_and_exam_lists_gain_only_granted_items(self):
        exams = [
            {"id": "q1", "courseId": "course-bio", "group": "grpBio"},
            {"id": "q2", "courseId": "course-other", "group": "grpBio"},
        ]
        with _grants(["course-bio"]), _course():
            courses = visibility.add_personally_assigned_courses(HEMA_USER, [], course_loader=lambda _id: COURSE)
            got = visibility.add_personally_assigned_exams(HEMA_USER, [], lambda: exams)
        self.assertEqual([c["id"] for c in courses], ["course-bio"])
        self.assertEqual([e["id"] for e in got], ["q1"])

    def test_no_grants_changes_nothing(self):
        with _grants([]):
            self.assertEqual(visibility.add_personally_assigned_exams(HEMA_USER, [{"id": "x"}], lambda: [{"id": "y", "courseId": "c"}]),
                             [{"id": "x"}])


class CrossGroupAssignmentRuleTests(unittest.TestCase):
    admin = {"username": "edu.admin", "role": "education_admin", "preferredArea": "internal", "preferredGroup": "grpBio"}
    leader = {"username": "leader.bio", "role": "group_leader", "preferredArea": "internal", "preferredGroup": "grpBio"}

    def _create(self, actor, account=HEMA_ACCOUNT):
        with patch("teacher_app.learning.assignment_service.auth_accounts.list_accounts", return_value=[account]), \
             patch("teacher_app.learning.assignment_service.assignment_repository.list_assignments", return_value=[]), \
             patch("teacher_app.learning.assignment_service.assignment_repository.insert_assignment",
                   side_effect=lambda v: {"id": v["id"], "assigneeType": v["assignee_type"], "assigneeKey": v["assignee_key"]}), \
             patch("teacher_app.learning.assignment_service.course_repository.get_course", return_value=COURSE):
            return assignment_service.create_assignment(
                actor, {"courseId": "course-bio", "assigneeType": "user", "assigneeKey": "student.hema"})

    def test_education_admin_can_assign_person_from_other_group(self):
        self.assertEqual(self._create(self.admin)["assigneeKey"], "student.hema")

    def test_group_leader_still_limited_to_own_group(self):
        with self.assertRaises(ApiError) as caught:
            self._create(self.leader)
        self.assertEqual(caught.exception.code, "ASSIGNEE_SCOPE_MISMATCH")

    def test_other_training_area_is_still_rejected_for_admin(self):
        with self.assertRaises(ApiError) as caught:
            self._create(self.admin, {**HEMA_ACCOUNT, "preferredArea": "pgy"})
        self.assertEqual(caught.exception.code, "ASSIGNEE_SCOPE_MISMATCH")

    def test_audience_options_list_other_groups_for_admin_only(self):
        accounts = [HEMA_ACCOUNT, {**HEMA_ACCOUNT, "username": "bio.person", "preferredGroup": "grpBio"}]
        with patch("teacher_app.learning.assignment_service.auth_accounts.list_accounts", return_value=accounts):
            admin = assignment_service.audience_options(self.admin, area="internal", group="grpBio")
            leader = assignment_service.audience_options(self.leader, area="internal", group="grpBio")
        self.assertEqual({p["username"] for p in admin["people"]}, {"student.hema", "bio.person"})
        self.assertEqual([p["username"] for p in admin["people"]][0], "bio.person")  # same group first
        self.assertTrue(next(p for p in admin["people"] if p["username"] == "student.hema")["crossGroup"])
        self.assertEqual({p["username"] for p in leader["people"]}, {"bio.person"})


if __name__ == "__main__":
    unittest.main()


class AssignmentQueryTests(unittest.TestCase):
    """Real SQL: an individual assignment follows the person, not the course's group."""

    def test_list_for_user_and_personal_ids_use_username_and_area_only(self):
        import os
        import sqlite3
        import tempfile

        from teacher_app.learning import assignment_repository as repo
        from teacher_app.maintenance.learning_assignment_migration import learning_assignments_83

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.db")
            with patch.dict(os.environ, {"TEACHER_SQLITE_PATH": path}):
                conn = sqlite3.connect(path)
                learning_assignments_83(conn, "sqlite")
                conn.commit()
                conn.close()
                for key, values in (("a1", ("grpBio", "internal")), ("a2", ("grpBio", "pgy"))):
                    repo.insert_assignment({
                        "id": key, "course_id": "course-" + key, "training_area": values[1], "group_key": values[0],
                        "assignee_type": "user", "assignee_key": "student.hema", "required": True, "due_at": "",
                        "assigned_at": "t", "assigned_by": "admin", "active": True, "created_at": "t", "updated_at": "t",
                    })
                rows = repo.list_for_user(username="Student.Hema", area="internal", group="grpHema")
                self.assertEqual([r["courseId"] for r in rows], ["course-a1"])
                self.assertEqual(repo.list_personal_course_ids(username="student.hema", area="internal"), ["course-a1"])
                self.assertEqual(repo.list_personal_course_ids(username="nobody", area="internal"), [])
