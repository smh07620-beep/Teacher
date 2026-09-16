import unittest

import pgy_workflow as legacy_workflow
from teacher_app.pgy import workflow as canonical_workflow


class PgyWorkflowTransitionTests(unittest.TestCase):
    def test_legacy_adapter_reexports_canonical_state_machine(self):
        self.assertIs(legacy_workflow.ASSIGNMENT_STATUSES, canonical_workflow.ASSIGNMENT_STATUSES)
        self.assertIs(legacy_workflow.WORKFLOW_TRANSITIONS, canonical_workflow.WORKFLOW_TRANSITIONS)
        self.assertIs(legacy_workflow.transition_allowed, canonical_workflow.transition_allowed)

    def test_happy_path_role_and_status_sequence(self):
        cases = [
            ("assigned", "submit", "student"),
            ("submitted", "teacher_sign", "clinical_teacher"),
            ("teacher_signed", "group_countersign", "group_leader"),
            ("group_countersigned", "finalize", "education_admin"),
        ]
        for status, action, role in cases:
            with self.subTest(status=status, action=action, role=role):
                self.assertTrue(canonical_workflow.transition_allowed(status, action, role))

    def test_system_admin_cannot_clinically_sign(self):
        self.assertFalse(canonical_workflow.transition_allowed("submitted", "teacher_sign", "system_admin"))

    def test_education_admin_cannot_skip_teacher_or_group_signature(self):
        self.assertFalse(canonical_workflow.transition_allowed("submitted", "finalize", "education_admin"))
        self.assertFalse(canonical_workflow.transition_allowed("teacher_signed", "finalize", "education_admin"))

    def test_wrong_status_cannot_repeat_signature(self):
        self.assertFalse(canonical_workflow.transition_allowed("teacher_signed", "teacher_sign", "clinical_teacher"))
        self.assertFalse(canonical_workflow.transition_allowed("finalized", "finalize", "education_admin"))

    def test_cancelled_is_terminal_for_normal_actions(self):
        for action, (_src, _dst, role) in canonical_workflow.WORKFLOW_TRANSITIONS.items():
            self.assertFalse(canonical_workflow.transition_allowed("cancelled", action, role))


if __name__ == "__main__":
    unittest.main()
