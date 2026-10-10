"""Editing a course must not blank out an already saved exam window / settings."""
import unittest
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / "static" / "course-wizard-681.js").read_text(encoding="utf-8")


class ExamWindowKeptTest(unittest.TestCase):
    def test_edit_flow_loads_saved_exam_settings(self):
        self.assertIn("await loadExistingExamSettings(category)", JS)
        self.assertIn("/api/exam-windows/", JS)
        self.assertIn("w.opens_at", JS)
        self.assertIn("w.closes_at", JS)

    def test_save_sends_only_touched_fields_and_merges_window(self):
        save = JS[JS.index("async function saveWizardExamSettings"):JS.index("window.courseWizard681SetExamField")]
        self.assertIn("touched.has('passingScore')", save)
        self.assertIn("touched.has('opensAt')", save)
        self.assertNotIn("passingScore:Math.max(1,Math.min(100,Number(v.passingScore)||80)),blindMode", save)
        self.assertIn("examTouchedFields", JS)


if __name__ == "__main__":
    unittest.main()
