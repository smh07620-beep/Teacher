import unittest
from teacher_app.common.auth import (
    CANONICAL_ROLES,
    LEGACY_ROLE_ALIASES,
    ROLE_PERMISSIONS,
    has_permission,
    normalize_role,
)


RBAC = {
    "CANONICAL_ROLES": CANONICAL_ROLES,
    "LEGACY_ROLE_ALIASES": LEGACY_ROLE_ALIASES,
    "ROLE_PERMISSIONS": ROLE_PERMISSIONS,
    "has_permission": has_permission,
    "normalize_role": normalize_role,
}


class RoleNormalizationTests(unittest.TestCase):
    def test_legacy_roles_resolve_to_canonical_roles(self):
        self.assertEqual(RBAC["normalize_role"]("learner"), "student")
        self.assertEqual(RBAC["normalize_role"]("teacher"), "clinical_teacher")
        self.assertEqual(RBAC["normalize_role"]("manager"), "education_admin")

    def test_all_six_canonical_roles_are_preserved(self):
        for role in RBAC["CANONICAL_ROLES"]:
            self.assertEqual(RBAC["normalize_role"](role), role)

    def test_unknown_role_fails_closed_to_student(self):
        self.assertEqual(RBAC["normalize_role"]("superuser"), "student")

    def test_auditor_has_no_mutation_permission(self):
        auditor = {"role": "auditor"}
        for permission in ("course.edit", "exam.manage", "evaluation.sign", "user.manage", "system.manage"):
            self.assertFalse(RBAC["has_permission"](auditor, permission))

    def test_system_admin_cannot_sign_clinical_evaluation(self):
        admin = {"role": "system_admin"}
        self.assertTrue(RBAC["has_permission"](admin, "system.manage"))
        self.assertFalse(RBAC["has_permission"](admin, "evaluation.sign"))

    def test_education_admin_cannot_impersonate_clinical_signer(self):
        admin = {"role": "education_admin"}
        self.assertTrue(RBAC["has_permission"](admin, "evaluation.finalize"))
        self.assertFalse(RBAC["has_permission"](admin, "evaluation.sign"))


if __name__ == "__main__":
    unittest.main()
