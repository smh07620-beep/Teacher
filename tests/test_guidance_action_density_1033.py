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

    def test_assessment_status_is_a_label_not_a_five_step_navigation(self):
        # 考卷已合成一頁：不再顯示「選考卷→發布」五步流程條，只留一個狀態標籤和一顆主按鈕。
        marker = 'id="exam-workflow-card"'
        start = self.system_html.index(marker)
        block = self.system_html[start:start + 700]
        self.assertIn('id="exam-workflow-status"', block)
        self.assertNotIn('data-stage=', block)
        self.assertNotIn('id="exam-workflow-steps"', self.system_html)
        self.assertIn('data-csp-click="examPrimaryAction()"', self.system_html)
        self.assertNotIn('data-csp-click="reviewCurrentExam()"', self.system_html)


if __name__ == "__main__":
    unittest.main()
