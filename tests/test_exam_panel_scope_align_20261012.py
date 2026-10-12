from pathlib import Path
import unittest

STATIC = Path(__file__).resolve().parents[1] / "static"


class ExamPanelAlignsScope(unittest.TestCase):
    def test_tool_panels_refetch_in_exam_own_scope(self):
        src = (STATIC / "teacher-content-tool-panels-710.js").read_text(encoding="utf-8")
        self.assertIn("'/api/quiz-categories/'+encodeURIComponent(catId)", src)
        self.assertIn("realGroup", src)

    def test_ai_panel_aligns_scope_before_giving_up(self):
        src = (STATIC / "teacher-content-studio-71.js").read_text(encoding="utf-8")
        self.assertIn("await alignExamScope(catId);\n          await timeout77", src)


if __name__ == "__main__":
    unittest.main()
