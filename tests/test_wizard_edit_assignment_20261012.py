from pathlib import Path
import unittest

SRC = (Path(__file__).resolve().parents[1] / "static" / "course-wizard-681.js").read_text(encoding="utf-8")


class EditNeverAutoAssigns(unittest.TestCase):
    def test_edit_open_disables_remembered_assignment(self):
        self.assertIn("state.editing=true;applyAssignMemory();state.assignmentEnabled=false;", SRC)

    def test_edit_mode_lists_existing_assignments(self):
        self.assertIn("loadExistingAssignmentsNote", SRC)
        self.assertIn("不會被清掉", SRC)


if __name__ == "__main__":
    unittest.main()
