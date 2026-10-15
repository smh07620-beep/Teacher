"""One rule: assigned (published, same-area) course => its course, materials and exams are visible.

Covers every account role x every assignment kind x same/other group, plus the exceptions
(unassigned, draft/inactive course, other area, source_only, per-view listing).
"""
import contextlib
import unittest
from unittest.mock import patch

from teacher_app.common import content_audience
from teacher_app.courses import visibility
from teacher_app.learning import access

COURSE = {"id": "course-bio", "area": "internal", "group": "grpBio", "active": True, "lifecycleStatus": "published"}
MATERIAL = {"id": "m1", "courseId": "course-bio", "area": "internal", "group": "grpBio", "active": True}
SOURCE_ONLY = {**MATERIAL, "id": "m2", "audienceScope": "source_only"}
LOOSE = {"id": "m3", "courseId": "", "area": "internal", "group": "grpBio", "active": True}
META = {"courseId": "course-bio", "ownerGroup": "grpBio", "audienceScope": "group_only", "audienceGroups": []}

ROLES = ("student", "clinical_teacher", "group_leader", "auditor")


def user(role, group="grpMicro", area="internal", name="u1"):
    return {"username": name, "role": role, "preferredArea": area, "preferredGroup": group}


@contextlib.contextmanager
def assigned(ids, course=COURSE):
    rows = [{"courseId": i} for i in ids]
    with patch("teacher_app.learning.assignment_repository.list_for_user", return_value=rows), \
         patch("teacher_app.courses.repository.get_course", return_value=course):
        yield


class AssignedCourseOpensEverythingTests(unittest.TestCase):
    def test_every_role_sees_material_course_and_visible_meta_when_assigned_from_other_group(self):
        for role in ROLES:
            with self.subTest(role=role), assigned(["course-bio"]):
                person = user(role)
                self.assertTrue(access.can_access_learning_item(person, MATERIAL))
                self.assertTrue(access.can_access_learning_item(person, COURSE))
                self.assertTrue(content_audience.visible_to_user(person, META))

    def test_assignment_kind_does_not_matter_because_the_rule_is_on_the_course(self):
        # user / group / all assignments all arrive as "this course is assigned to the person".
        with assigned(["course-bio"]):
            self.assertIn("course-bio", access.assigned_course_grants(user("student")))
            self.assertIn("course-bio", access.assigned_course_ids(user("student")))

    def test_without_assignment_other_group_content_stays_hidden(self):
        for role in ROLES:
            with self.subTest(role=role), assigned([]):
                person = user(role)
                self.assertFalse(access.can_access_learning_item(person, MATERIAL))
                self.assertFalse(content_audience.visible_to_user(person, META))

    def test_only_the_assigned_course_opens(self):
        other = {**MATERIAL, "id": "mx", "courseId": "course-other"}
        with assigned(["course-bio"]):
            self.assertFalse(access.can_access_learning_item(user("student"), other))

    def test_draft_or_inactive_course_grants_nothing(self):
        for course in ({**COURSE, "lifecycleStatus": "draft"}, {**COURSE, "active": False}):
            with self.subTest(course=course), assigned(["course-bio"], course):
                self.assertFalse(access.can_access_learning_item(user("student"), MATERIAL))

    def test_other_training_area_grants_nothing(self):
        with assigned(["course-bio"], {**COURSE, "area": "pgy"}):
            self.assertFalse(access.can_access_learning_item(user("student"), MATERIAL))

    def test_source_only_material_is_never_shown_to_learners(self):
        with assigned(["course-bio"]):
            for role in ("student", "group_leader"):
                self.assertFalse(access.can_access_learning_item(user(role), SOURCE_ONLY))

    def test_same_group_people_are_unaffected(self):
        with assigned(["course-bio"]):
            self.assertTrue(access.can_access_learning_item(user("student", "grpBio"), MATERIAL))

    def test_content_outside_any_course_still_follows_group_and_audience(self):
        with assigned(["course-bio"]):
            self.assertFalse(access.can_access_learning_item(user("student"), LOOSE))
            self.assertTrue(access.can_access_learning_item(user("student", "grpBio"), LOOSE))

    def test_admins_keep_global_access(self):
        with assigned([]):
            for role in ("education_admin", "system_admin"):
                self.assertTrue(access.can_access_learning_item(user(role), MATERIAL))


class ViewScopingTests(unittest.TestCase):
    EXAMS = [{"id": "q1", "courseId": "course-bio", "group": "grpBio"},
             {"id": "q2", "courseId": "course-other", "group": "grpBio"}]

    def _courses(self, group):
        with assigned(["course-bio"]):
            return visibility.add_personally_assigned_courses(
                user("student"), [], course_loader=lambda _id: COURSE, requested_group=group)

    def _exams(self, group):
        with assigned(["course-bio"]):
            return visibility.add_personally_assigned_exams(
                user("student"), [], lambda: self.EXAMS, requested_group=group)

    def test_assigned_course_and_exam_show_in_owner_and_own_group_views(self):
        for group in ("grpBio", "grpMicro"):
            self.assertEqual([c["id"] for c in self._courses(group)], ["course-bio"], group)
            self.assertEqual([e["id"] for e in self._exams(group)], ["q1"], group)

    def test_assigned_course_does_not_leak_into_an_unrelated_group_tab(self):
        self.assertEqual(self._courses("grpBB"), [])
        self.assertEqual(self._exams("grpBB"), [])

    def test_no_requested_group_keeps_old_behaviour(self):
        self.assertEqual([c["id"] for c in self._courses(None)], ["course-bio"])


class RealSqlAssignmentKindsTests(unittest.TestCase):
    """Real SQL: all-staff and own-group assignments reach the person like an individual one."""

    def test_all_group_and_user_assignments_each_make_the_course_assigned(self):
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
                for key, kind, who, group in (
                    ("a-all", "all", "*", "grpBio"),
                    ("a-grp", "group", "grpMicro", "grpMicro"),
                    ("a-usr", "user", "u1", "grpBio"),
                ):
                    repo.insert_assignment({
                        "id": key, "course_id": "course-" + key, "training_area": "internal", "group_key": group,
                        "assignee_type": kind, "assignee_key": who, "required": True, "due_at": "",
                        "assigned_at": "t", "assigned_by": "admin", "active": True, "created_at": "t", "updated_at": "t",
                    })
                rows = repo.list_for_user(username="u1", area="internal", group="grpMicro")
                self.assertEqual({r["courseId"] for r in rows}, {"course-a-all", "course-a-grp", "course-a-usr"})
                other = repo.list_for_user(username="someone", area="internal", group="grpBB")
                self.assertEqual({r["courseId"] for r in other}, {"course-a-all"})


if __name__ == "__main__":
    unittest.main()
