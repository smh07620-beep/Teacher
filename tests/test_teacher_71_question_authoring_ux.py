"""Teacher 7.1/7.2 question-authoring and learner-page UX regressions."""
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class QuestionAuthoringUx71Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authoring = ROOT.joinpath("static", "question-authoring-ux-71.js").read_text(encoding="utf-8")
        cls.learner = ROOT.joinpath("static", "learner-ui-cleanup-71.js").read_text(encoding="utf-8")
        cls.frontend = ROOT.joinpath("pgy_frontend.py").read_text(encoding="utf-8")
        cls.workflow = ROOT.joinpath(".github", "workflows", "phase3-pgy-checks.yml").read_text(encoding="utf-8")

    def test_teacher_editor_is_chinese_and_progressively_disclosed(self):
        for marker in (
            "主題", "子主題", "學習目標", "難度", "認知層次", "來源定位方式",
            "進階設定（選填）", "正確答案", "文件／PDF 頁碼", "影片時間",
        ):
            self.assertIn(marker, self.authoring)
        for english_label in (
            "renameLabel('qb681-topic', 'Topic')",
            "renameLabel('qb681-subtopic', 'Subtopic')",
            "renameLabel('qb681-objective', 'Learning objective')",
            "renameLabel('qb681-difficulty', 'Difficulty')",
            "renameLabel('qb681-cognitive', 'Cognitive level')",
            "renameLabel('qb681-rstype', 'ReviewSource 類型')",
        ):
            self.assertNotIn(english_label, self.authoring)

    def test_save_closes_only_after_success_and_cancel_is_explicit(self):
        self.assertIn("const result = await originalSave()", self.authoring)
        self.assertIn("if (result) window.assessment681CloseQuestion?.()", self.authoring)
        self.assertIn("cancel.textContent = '取消'", self.authoring)
        self.assertIn("save.textContent = '💾 儲存題目'", self.authoring)

    def test_delete_resolves_category_for_scoped_rbac(self):
        self.assertIn("const bank = await api('/api/question-bank')", self.authoring)
        self.assertIn("item?.quizCategoryId", self.authoring)
        self.assertIn("?quizCategoryId=${encodeURIComponent(category)}", self.authoring)
        self.assertIn("method: 'DELETE'", self.authoring)
        self.assertIn("🗑️ 刪除此題", self.authoring)

    def test_workflow_state_is_not_normal_teacher_input(self):
        self.assertIn("['qb681-status', 'qb681-origin']", self.authoring)
        self.assertIn("classList.add('hidden')", self.authoring)
        self.assertIn("題目狀態", self.authoring)
        self.assertIn("題目來源", self.authoring)

    def test_assessment_surface_is_management_only(self):
        self.assertIn("button.textContent = '考卷管理'", self.authoring)
        self.assertIn("button.textContent = '已建立題目'", self.authoring)
        self.assertIn("else { button.classList.add('hidden')", self.authoring)
        self.assertIn('新增題目、AI 輔助出題、圖片題與影片題統一從「＋ 建立教學內容」開始', self.authoring)
        self.assertIn('/teacher-ux-convergence-72.js?v=7202', self.authoring)

    def test_learner_page_removes_redundant_instruction_blocks(self):
        self.assertIn("const intro = slidesPanel.querySelector(':scope > section.edu-card')", self.learner)
        self.assertIn("learningStart.replaceChildren()", self.learner)
        self.assertIn("learningStart.dataset.ready = '1'", self.learner)
        self.assertIn("header?.querySelector('.edu-kicker')?.remove()", self.learner)
        self.assertIn("if (desc?.tagName === 'P') hide(desc)", self.learner)
        self.assertIn("if (String(resultCount.textContent || '').trim()) show(resultCount)", self.learner)

    def test_assets_are_composed_and_syntax_checked(self):
        self.assertIn('/question-authoring-ux-71.js?v=7132', self.frontend)
        self.assertIn('/teacher-ux-convergence-72.js?v=7202', self.frontend)
        self.assertIn('/learner-ui-cleanup-71.js?v=7131', self.frontend)
        self.assertLess(
            self.frontend.index('/question-authoring-ux-71.js?v=7132'),
            self.frontend.index('/teacher-ux-convergence-72.js?v=7202'),
        )
        self.assertLess(
            self.frontend.index('/teacher-ux-convergence-72.js?v=7202'),
            self.frontend.index('/admin-compat-facade.js?v=7300'),
        )
        self.assertIn('node --check static/question-authoring-ux-71.js', self.workflow)
        self.assertIn('node --check static/learner-ui-cleanup-71.js', self.workflow)


if __name__ == "__main__":
    unittest.main()
