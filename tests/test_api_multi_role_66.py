import unittest

from multi_role_66 import (
    register_multi_role_66,
)
from tests.auth_support import AuthFixture


class MultiRoleApi66Tests(
    AuthFixture
):
    def setUp(self):
        super().setUp()

        register_multi_role_66(
            self.base
        )

    def test_create_account_with_multiple_roles(self):
        response = self.client.post(
            "/api/users",
            json={
                "username": "multi1",
                "password": "1234",
                "name": "Multi Role",
                "empId": "M001",
                "role":
                    "clinical_teacher",
                "roles": [
                    "clinical_teacher",
                    "group_leader",
                ],
                "preferredArea":
                    "internal",
                "preferredGroup":
                    "grpBio",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
            response.get_data(
                as_text=True
            ),
        )

        user = response.get_json()[
            "user"
        ]

        self.assertEqual(
            user["role"],
            "clinical_teacher",
        )

        self.assertEqual(
            user["roles"],
            [
                "clinical_teacher",
                "group_leader",
            ],
        )

    def test_update_roles_invalidates_existing_session(self):
        self.assertEqual(
            self.login().status_code,
            200,
        )

        updated = self.client.patch(
            "/api/users/teacher1",
            json={
                "role":
                    "clinical_teacher",
                "roles": [
                    "clinical_teacher",
                    "group_leader",
                ],
            },
        )

        self.assertEqual(
            updated.status_code,
            200,
        )

        self.assertEqual(
            updated.get_json()[
                "user"
            ]["roles"],
            [
                "clinical_teacher",
                "group_leader",
            ],
        )

        me = self.client.get(
            "/api/auth/me"
        )

        self.assertFalse(
            me.get_json()[
                "authenticated"
            ]
        )

    def test_legacy_role_only_update_remains_single_role(self):
        response = self.client.patch(
            "/api/users/teacher1",
            json={
                "role":
                    "group_leader"
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        user = response.get_json()[
            "user"
        ]

        self.assertEqual(
            user["role"],
            "group_leader",
        )

        self.assertEqual(
            user["roles"],
            ["group_leader"],
        )


if __name__ == "__main__":
    unittest.main()
