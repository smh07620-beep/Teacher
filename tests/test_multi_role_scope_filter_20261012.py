"""A 教學管理者/系統管理者 who is also 組長 must not be narrowed to one group (2026-10-12)."""
import json
import unittest
from unittest import mock

from flask import Flask, jsonify

from teacher_app.common import scope_filter

ROWS = [
    {"id": "c1", "group": "grpBio", "area": "internal", "title": "bio"},
    {"id": "c2", "group": "grpMicro", "area": "internal", "title": "micro"},
]


def user(*roles, group="grpBio"):
    return {"username": "u", "role": roles[0], "roles": list(roles), "preferredArea": "internal", "preferredGroup": group}


def run(who, endpoint="api_courses_admin"):
    app = Flask(__name__)
    app.add_url_rule("/rows", endpoint=endpoint, view_func=lambda: jsonify(ROWS))
    app.after_request(lambda response: scope_filter.filter_scoped_response(app, response))
    with mock.patch.object(scope_filter, "_current_user", return_value=who):
        response = app.test_client().get("/rows")
    return [row["id"] for row in json.loads(response.get_data(as_text=True))]


class MultiRoleScopeFilterTests(unittest.TestCase):
    def test_pure_group_leader_stays_in_own_group(self):
        self.assertEqual(run(user("group_leader")), ["c1"])

    def test_clinical_teacher_stays_in_own_group(self):
        self.assertEqual(run(user("clinical_teacher")), ["c1"])

    def test_education_admin_who_is_also_group_leader_sees_every_group(self):
        self.assertEqual(run(user("group_leader", "education_admin")), ["c1", "c2"])

    def test_system_admin_who_is_also_group_leader_sees_every_group(self):
        self.assertEqual(run(user("group_leader", "system_admin")), ["c1", "c2"])

    def test_all_three_roles_see_every_group(self):
        self.assertEqual(run(user("group_leader", "education_admin", "system_admin")), ["c1", "c2"])


if __name__ == "__main__":
    unittest.main()
