"""Teacher question-authoring and learner-page UX regressions after runtime convergence."""
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]

class QuestionAuthoringUx71Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retired_overlay = ROOT.joinpath("static", "question-authoring-ux-71.js").read_text(encoding="utf-8")
        cls.editor = ROOT.joinpath("static", "admin-question-editor-ui.js").read_text(encoding="utf-8")
        cls.actions = ROOT.joinpath("static", "admin-question-actions.js").read_text(encoding="utf-8")
        cls.panel = ROOT.joinpath("static", "admin-question-panel.js").read_text(encoding="utf-8")
        cls.assessment_compat = ROOT.joinpath("static", "assessment-681.js").read_text(encoding="utf-8")
        cls.learner = ROOT.joinpath("static", "learner-ui-cleanup-71.js").read_text(encoding="utf-8")
        cls.learner_css = ROOT.joinpath("static", "learner-layout-stability-73.css").read_text(encoding="utf-8")
        cls.frontend = ROOT.joinpath("pgy_frontend.py").read_text(encoding="utf-8")
        cls.workflow = ROOT.joinpath(".github", "workflows", "phase3-pgy-checks.yml").read_text(encoding="utf-8")

    def test_canonical_editor_is_chinese_and_supports_all_primary_question_types(self):
        for marker in (
            "編輯題目", "題目類型", "難度", "題目分類", "正確答案",
            "單選題", "複選題", "是非題", "問答題", "填空題", "圖片判讀題", "影片題",
            "💾 儲存此題",
        ):
            self.assertIn(marker, self.editor)

    def test_canonical_actions_own_save_delete_and_bulk_delete(self):
        for marker in (
            "adminSaveOneInlineQuestion", "adminDeleteQuizQuestion", "adminBulkDeleteQuestions",
            "確定刪除此題目？此操作無法復原。", "method:'DELETE'", "method:'PATCH'",
        ):
            self.assertIn(marker, self.actions)
        self.assertIn("adminDeleteQuizCategory", self.panel)
        self.assertIn("頁籤內所有題目也會一併刪除", self.panel)

    def test_old_question_drawer_overlay_is_physically_retired(self):
        self.assertIn("Retired by Teacher runtime convergence", self.retired_overlay)
        self.assertIn("canonicalOwner", self.retired_overlay)
        for forbidden in ("qb681-", "assessment681SaveQuestion", "assessment681Delete", "fetch(", "/api/question-bank", "question-bank-drawer"):
            self.assertNotIn(forbidden, self.retired_overlay)

    def test_old_assessment_router_no_longer_creates_second_management_surface(self):
        self.assertIn("Compatibility router after Teacher runtime convergence", self.assessment_compat)
        self.assertIn("openCanonicalAssessment", self.assessment_compat)
        self.assertNotIn("insertAdjacentHTML", self.assessment_compat)
        self.assertNotIn("assessment-681-body", self.assessment_compat)
        self.assertNotIn("question-bank-drawer", self.assessment_compat)

    def test_learner_page_removes_redundant_instruction_blocks_without_observer(self):
        self.assertIn("const intro = slidesPanel.querySelector(':scope > section.edu-card')", self.learner)
        self.assertIn("learningStart.replaceChildren()", self.learner)
        self.assertIn("learningStart.dataset.ready = '1'", self.learner)
        self.assertIn("header?.querySelector('.edu-kicker')?.remove()", self.learner)
        self.assertIn("if (desc?.tagName === 'P') hide(desc)", self.learner)
        self.assertNotIn('new MutationObserver', self.learner)
        self.assertIn('#panel-slides > section.edu-card:first-child', self.learner_css)
        self.assertIn('#learning-start', self.learner_css)
        self.assertIn('#course-overview > .edu-card .edu-kicker', self.learner_css)

    def test_compatibility_assets_remain_syntax_checked_for_one_cycle(self):
        self.assertIn('/question-authoring-ux-71.js?v=7133', self.frontend)
        self.assertIn('/learner-layout-stability-73.css?v=7300', self.frontend)
        self.assertIn('/learner-ui-cleanup-71.js?v=7132', self.frontend)
        self.assertIn('node --check static/question-authoring-ux-71.js', self.workflow)
        self.assertIn('node --check static/assessment-681.js', self.workflow)
        self.assertIn('node --check static/assessment-advanced-74.js', self.workflow)

if __name__ == "__main__":
    unittest.main()
