import unittest

from teacher_app.learning import assignment_routes


class GroupLeaderAllScopeTests(unittest.TestCase):
    def test_group_leader_ui_can_offer_all_but_scope_is_marked_course_group(self):
        actor = {
            "username": "leader.bio",
            "role": "group_leader",
            "roles": ["group_leader"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }
        options = assignment_routes._audience_options_for_actor(
            actor,
            {
                "area": "internal",
                "group": "grpBio",
                "groups": [{"key": "grpBio", "label": "生化組"}],
                "people": [],
                "allowedAssigneeTypes": ["group", "user"],
            },
        )
        self.assertEqual(options["allowedAssigneeTypes"], ["group", "user", "all"])
        self.assertEqual(options["allScope"], "course_group")

    def test_group_leader_all_is_normalized_to_course_scoped_group_assignment(self):
        actor = {
            "username": "leader.bio",
            "role": "group_leader",
            "roles": ["group_leader"],
        }
        payload = assignment_routes._normalize_create_payload(
            actor,
            {"courseId": "course-bio", "assigneeType": "all", "assigneeKey": "*"},
        )
        self.assertEqual(payload["courseId"], "course-bio")
        self.assertEqual(payload["assigneeType"], "group")
        self.assertEqual(payload["assigneeKey"], "")

    def test_global_manager_keeps_real_organization_all_assignment(self):
        actor = {
            "username": "leader.admin",
            "role": "group_leader",
            "roles": ["group_leader", "education_admin"],
        }
        payload = assignment_routes._normalize_create_payload(
            actor,
            {"courseId": "course-bio", "assigneeType": "all", "assigneeKey": "*"},
        )
        self.assertEqual(payload["assigneeType"], "all")
        self.assertEqual(payload["assigneeKey"], "*")


if __name__ == "__main__":
    unittest.main()
