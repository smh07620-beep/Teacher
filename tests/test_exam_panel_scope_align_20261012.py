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


class ManualToolsStayInStudio(unittest.TestCase):
    def test_latency_script_does_not_override_in_studio_manual_tool(self):
        src = (STATIC / "teacher-content-latency-712.js").read_text(encoding="utf-8")
        self.assertIn("if(!window.TeacherContentToolPanels710?.openManual){", src)


class EmbeddedExamSettingsActionsVisible(unittest.TestCase):
    def test_publish_bar_is_not_force_hidden_inside_the_exam_page(self):
        css = (STATIC / "portal.css").read_text(encoding="utf-8")
        self.assertIn("#admin-modal [data-exam-embedded] #exam-settings-actions{display:flex!important}", css)
