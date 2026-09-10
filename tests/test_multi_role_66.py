import unittest

from teacher_app.common.auth import (
    has_permission,
    has_role,
    normalize_roles,
    require_role,
)
from teacher_app.common.errors import ApiError


class MultiRole66Tests(
    unittest.TestCase
):
    def test_legacy_single_role_still_works(self):
        user = {
            "role": "teacher"
        }

        self.assertEqual(
            normalize_roles(
                None,
                primary=user["role"],
            ),
            ["clinical_teacher"],
        )

        self.assertTrue(
            has_permission(
                user,
                "evaluation.sign",
            )
        )

    def test_multiple_roles_are_normalized_and_deduplicated(self):
        roles = normalize_roles(
            [
                "teacher",
                "group_leader",
                "clinical_teacher",
            ],
            primary="teacher",
        )

        self.assertEqual(
            roles,
            [
                "clinical_teacher",
                "group_leader",
            ],
        )

    def test_multi_role_user_has_union_of_permissions(self):
        user = {
            "role": "clinical_teacher",
            "roles": [
                "clinical_teacher",
                "group_leader",
            ],
        }

        self.assertTrue(
            has_permission(
                user,
                "evaluation.sign",
            )
        )

        self.assertTrue(
            has_permission(
                user,
                "evaluation.countersign",
            )
        )

        self.assertTrue(
            has_role(
                user,
                "group_leader",
            )
        )

    def test_admin_roles_alone_still_cannot_clinically_sign(self):
        user = {
            "role": "education_admin",
            "roles": [
                "education_admin",
                "system_admin",
            ],
        }

        self.assertFalse(
            has_permission(
                user,
                "evaluation.sign",
            )
        )

    def test_admin_plus_real_clinical_role_can_sign_as_that_role(self):
        user = {
            "role": "education_admin",
            "roles": [
                "education_admin",
                "clinical_teacher",
            ],
        }

        self.assertTrue(
            has_permission(
                user,
                "evaluation.sign",
            )
        )

    def test_require_role_accepts_secondary_role(self):
        user = {
            "role": "clinical_teacher",
            "roles": [
                "clinical_teacher",
                "group_leader",
            ],
        }

        self.assertIs(
            require_role(
                user,
                "group_leader",
            ),
            user,
        )

    def test_require_role_rejects_missing_role(self):
        user = {
            "role": "education_admin",
            "roles": [
                "education_admin",
                "system_admin",
            ],
        }

        with self.assertRaises(
            ApiError
        ) as denied:
            require_role(
                user,
                "clinical_teacher",
            )

        self.assertEqual(
            denied.exception.status,
            403,
        )


if __name__ == "__main__":
    unittest.main()
