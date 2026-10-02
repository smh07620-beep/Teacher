import unittest
from pathlib import Path

from pgy_frontend import ASSET_MANIFEST


ROOT = Path(__file__).parents[1]


class ProductUxConvergencePhaseDTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.queue = ROOT.joinpath("static", "teacher-action-queue-1024.js").read_text(encoding="utf-8")
        cls.product = ROOT.joinpath("static", "product-convergence-101.js").read_text(encoding="utf-8")
        cls.teacher = ROOT.joinpath("static", "teacher-workspace-1014.js").read_text(encoding="utf-8")
        cls.course = ROOT.joinpath("static", "admin-course-material.js").read_text(encoding="utf-8")
        cls.quiz = ROOT.joinpath("static", "admin-question-bank.js").read_text(encoding="utf-8")
        cls.home = ROOT.joinpath("static", "index.html").read_text(encoding="utf-8")

    def test_teacher_action_queue_follows_active_workspace_without_duplicate_state_owner(self):
        for marker in (
            "function currentContext()",
            "admin-section-content",
            "admin-section-quiz",
            "admin-section-results",
            "item.kind === 'review'",
            "item.kind !== 'review'",
            "section.dataset.productSection = 'needs-action'",
            "/api/training-command-center",
        ):
            self.assertIn(marker, self.queue)
        self.assertNotIn("X-Admin-Key", self.queue)
        self.assertNotIn("getAdminKey", self.queue)

    def test_course_workspace_exposes_overview_current_work_and_human_history(self):
        self.assertIn('data-product-section="overview"', self.course)
        self.assertIn('data-product-section="current-work"', self.course)
        self.assertIn("function ensureTeacherMaterialHistory()", self.product)
        self.assertIn("panel.dataset.productSection = 'history'", self.product)
        self.assertIn("教材處理紀錄", self.product)
        self.assertIn("需要技術細節時再展開", self.product)

    def test_assessment_workspace_uses_queue_for_actions_and_shortcut_for_history(self):
        self.assertIn("setAttribute('data-product-section','overview')", self.quiz)
        self.assertIn("box.dataset.productSection='current-work'", self.quiz)
        self.assertIn("section.dataset.productSection = 'history'", self.teacher)
        self.assertIn("歷史紀錄", self.teacher)
        self.assertIn("待批改項目改由上方「需要我處理」直接進入", self.teacher)
        self.assertIn("switchAdminWorkspace?.('results', true)", self.teacher)

    def test_learner_home_uses_the_same_four_section_contract(self):
        self.assertIn('id="today-learning" data-product-section="overview"', self.home)
        self.assertIn('id="groups" data-product-section="current-work"', self.home)
        self.assertIn('data-product-section="history" class="v56-panel phase3-content-panel"', self.home)
        self.assertIn('id="pending-exams" data-product-section="needs-action"', self.home)

    def test_phase_d_layers_load_after_existing_workspace_owners(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertLess(body.index("/teacher-workspace-1014.js"), body.index("/product-convergence-101.js"))
        self.assertLess(body.index("/product-convergence-101.js"), body.index("/teacher-action-queue-1024.js"))


if __name__ == "__main__":
    unittest.main()
