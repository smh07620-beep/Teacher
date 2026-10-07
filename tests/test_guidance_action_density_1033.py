from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GuidanceActionDensity1033Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = (ROOT / "static" / "teacher-workspace-1014.js").read_text(encoding="utf-8")
        cls.media_help = (ROOT / "static" / "teacher-media-help-1014.js").read_text(encoding="utf-8")
        cls.media_studio = (ROOT / "static" / "teacher-ai-media-studio-1018.js").read_text(encoding="utf-8")
        cls.system_html = (ROOT / "static" / "system.html").read_text(encoding="utf-8")

    def test_teacher_quick_start_cards_are_explanatory_without_a_second_create_course_action(self):
        start = self.workspace.index("function guideCard")
        end = self.workspace.index("function showTeacherGuide", start)
        guide = self.workspace[start:end]
        self.assertNotIn("data-teacher-guide-action", guide)
        # The workspace's own 「＋ 建立課程」 is the single create-course entry.
        self.assertNotIn('teacher-guide-start-course-1014', guide)
        card_fn = guide[:guide.index("function ensureTeacherGuide")]
        self.assertNotIn("<button", card_fn)

    def test_media_help_cards_do_not_embed_actions(self):
        start = self.media_help.index("panel.innerHTML")
        end = self.media_help.index("shell.insertAdjacentElement", start)
        panel = self.media_help[start:end]
        self.assertNotIn("<button", panel)
        for label in ("AI PowerPoint", "講稿與配音", "老師自己錄影", "AI 教學影片"):
            self.assertIn(label, panel)

    def test_media_mode_guides_use_labels_not_step_buttons(self):
        self.assertIn("steps.map((step,index)=>`<span", self.media_studio)
        self.assertNotIn("steps.map((step,index)=>`<button", self.media_studio)

    def test_assessment_workflow_stepper_is_status_not_navigation(self):
        marker = 'id="exam-workflow-card"'
        start = self.system_html.index(marker)
        block = self.system_html[start:start + 1200]
        self.assertIn('id="exam-workflow-steps"', block)
        self.assertIn('<span data-stage="select">1 選考卷</span>', block)
        self.assertNotIn('data-stage="select"><button', block)


if __name__ == "__main__":
    unittest.main()
