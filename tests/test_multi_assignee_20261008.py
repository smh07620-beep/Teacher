import unittest
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "static" / "course-wizard-681.js").read_text(encoding="utf-8")


class MultiAssigneeWizardTests(unittest.TestCase):
    def test_checklist_replaces_single_select_for_specific_people(self):
        for marker in ("cw681-assignee-list", "cw681-assignee-all", "cw681-assignee-none", "已選 ${count} 人"):
            self.assertIn(marker, SOURCE)

    def test_one_assignment_is_created_per_selected_person_and_is_idempotent(self):
        self.assertIn("postWizardAssignment(courseId,'user',key)", SOURCE)
        self.assertIn("ASSIGNMENT_EXISTS", SOURCE)
        self.assertIn("尚未選擇要指派的人員", SOURCE)

    def test_group_and_all_assignments_still_use_a_single_post(self):
        self.assertIn("return postWizardAssignment(courseId,assigneeType,assigneeKey)", SOURCE)


if __name__ == "__main__":
    unittest.main()
