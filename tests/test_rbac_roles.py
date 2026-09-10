import ast
import unittest
from pathlib import Path


def load_rbac_namespace():
    source = Path(__file__).parents[1].joinpath("app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    selected = []
    names = {"LEGACY_ROLE_ALIASES", "CANONICAL_ROLES", "ROLE_PERMISSIONS"}
    functions = {"normalize_role", "has_permission"}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "teacher_app.common.auth":
            selected.append(node)
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in functions:
            selected.append(node)
    namespace = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "app.py", "exec"), namespace)
    return namespace


RBAC = load_rbac_namespace()


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
