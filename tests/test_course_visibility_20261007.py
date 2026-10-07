"""Learners must not get empty course shells for materials they cannot see."""
import unittest

from teacher_app.courses.visibility import filter_courses_for_user


def course(cid, group="grpBio", area="internal"):
    return {"id": cid, "group": group, "area": area, "title": cid}


def material(mid, course_id, group="grpBio", area="internal"):
    return {"id": mid, "courseId": course_id, "group": group, "area": area}


def user(group="grpMicro", area="internal", roles=("student",)):
    return {"username": "u", "preferredGroup": group, "preferredArea": area, "roles": list(roles), "role": roles[0]}


def metas(mapping):
    return lambda ids: {i: mapping[i] for i in ids if i in mapping}


def meta(owner="grpBio", scope="group_only", groups=()):
    return {"ownerGroup": owner, "audienceScope": scope, "audienceGroups": list(groups)}


class CourseVisibilityTests(unittest.TestCase):
    def run_filter(self, who, courses, materials, meta_map):
        return [c["id"] for c in filter_courses_for_user(
            who, courses, material_loader=lambda: materials, meta_loader=metas(meta_map))]

    def test_other_group_does_not_get_an_empty_shell_for_group_only_materials(self):
        result = self.run_filter(user("grpMicro"), [course("c1")], [material("m1", "c1")], {"m1": meta()})
        self.assertEqual(result, [])

    def test_same_group_sees_own_course_even_without_materials(self):
        self.assertEqual(self.run_filter(user("grpBio"), [course("c1")], [], {}), ["c1"])

    def test_shared_all_staff_material_brings_its_course_along(self):
        result = self.run_filter(user("grpMicro"), [course("c1")], [material("m1", "c1")], {"m1": meta(scope="all_staff")})
        self.assertEqual(result, ["c1"])

    def test_multi_group_sharing_only_reaches_listed_groups(self):
        shared = {"m1": meta(scope="multi_group", groups=["grpSero"])}
        self.assertEqual(self.run_filter(user("grpSero"), [course("c1")], [material("m1", "c1")], shared), ["c1"])
        self.assertEqual(self.run_filter(user("grpMicro"), [course("c1")], [material("m1", "c1")], shared), [])

    def test_materials_of_other_courses_do_not_unlock_a_course(self):
        result = self.run_filter(
            user("grpMicro"), [course("c1"), course("c2")],
            [material("m1", "c2")], {"m1": meta(scope="all_staff")})
        self.assertEqual(result, ["c2"])

    def test_different_training_area_never_matches(self):
        result = self.run_filter(user("grpBio", area="pgy"), [course("c1", area="internal")], [], {})
        self.assertEqual(result, [])

    def test_managers_and_scopeless_fixtures_keep_the_full_list(self):
        courses = [course("c1"), course("c2", group="grpMicro")]
        for who in (user("grpSero", roles=("education_admin",)), user("grpSero", roles=("system_admin",)),
                    {"username": "legacy", "roles": ["student"]}):
            self.assertEqual(self.run_filter(who, courses, [], {}), ["c1", "c2"])

    def test_anonymous_gets_nothing(self):
        self.assertEqual(filter_courses_for_user(None, [course("c1")]), [])


class RouteWiringTests(unittest.TestCase):
    def test_learner_course_list_uses_the_filter_and_admin_list_does_not(self):
        from pathlib import Path
        source = Path(__file__).parents[1].joinpath("teacher_app", "legacy_host.py").read_text(encoding="utf-8")
        learner = source[source.index('@app.get("/api/courses")'):source.index('@app.get("/api/courses/admin")')]
        admin = source[source.index('@app.get("/api/courses/admin")'):source.index('@app.post("/api/courses")')]
        self.assertIn("filter_courses_for_user(_current_user(), courses)", learner)
        self.assertNotIn("filter_courses_for_user", admin)


if __name__ == "__main__":
    unittest.main()
