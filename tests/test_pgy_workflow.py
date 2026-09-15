import ast
import unittest
from pathlib import Path


def load_workflow_namespace():
    source = Path(__file__).parents[1].joinpath("pgy_workflow.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    selected = []
    names = {"ASSIGNMENT_STATUSES", "WORKFLOW_TRANSITIONS"}
    functions = {"transition_allowed"}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in functions:
            selected.append(node)
    namespace = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "pgy_workflow.py", "exec"), namespace)
    return namespace


WF = load_workflow_namespace()


class PgyWorkflowTransitionTests(unittest.TestCase):
    def test_happy_path_role_and_status_sequence(self):
        cases = [
            ("assigned", "submit", "student"),
            ("submitted", "teacher_sign", "clinical_teacher"),
            ("teacher_signed", "group_countersign", "group_leader"),
            ("group_countersigned", "finalize", "education_admin"),
        ]
        for status, action, role in cases:
            with self.subTest(status=status, action=action, role=role):
                self.assertTrue(WF["transition_allowed"](status, action, role))

    def test_system_admin_cannot_clinically_sign(self):
        self.assertFalse(WF["transition_allowed"]("submitted", "teacher_sign", "system_admin"))

    def test_education_admin_cannot_skip_teacher_or_group_signature(self):
        self.assertFalse(WF["transition_allowed"]("submitted", "finalize", "education_admin"))
        self.assertFalse(WF["transition_allowed"]("teacher_signed", "finalize", "education_admin"))

    def test_wrong_status_cannot_repeat_signature(self):
        self.assertFalse(WF["transition_allowed"]("teacher_signed", "teacher_sign", "clinical_teacher"))
        self.assertFalse(WF["transition_allowed"]("finalized", "finalize", "education_admin"))

    def test_cancelled_is_terminal_for_normal_actions(self):
        for action, (_src, _dst, role) in WF["WORKFLOW_TRANSITIONS"].items():
            self.assertFalse(WF["transition_allowed"]("cancelled", action, role))


if __name__ == "__main__":
    unittest.main()
