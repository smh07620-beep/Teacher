"""2026-10-09: 考卷合併成一頁、教材區對齊、配音標記與移除、PGY 學員區塊精簡。"""
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


def read(name):
    return ROOT.joinpath("static", name).read_text(encoding="utf-8")


class ExamSinglePageTests(unittest.TestCase):
    def test_exam_card_only_has_enter_and_overflow(self):
        js = read("admin-question-bank.js")
        start = js.index("function quizCategoryCardHTML")
        card = js[start:js.index('<div id="qpanel-', start)]
        self.assertIn(">進入</button>", card)
        self.assertIn("window.openTeacherContentExam?.('${c.id}')", card)
        self.assertNotIn("管理（設定／發布）", card)
        self.assertIn("adminDeleteQuizCategory", card)

    def test_exam_page_embeds_questions_and_settings(self):
        studio = read("teacher-content-studio-71.js")
        self.assertIn("data-exam-questions-slot", studio)
        self.assertIn("data-exam-settings-slot", studio)
        self.assertIn("mountQuestionsInline?.(catId,qSlot)", studio)
        self.assertIn("mountExamSettingsInline(catId,sSlot)", studio)
        self.assertIn("restoreExamSettings();", studio)
        panels = read("teacher-content-tool-panels-710.js")
        self.assertIn("async function mountQuestionsInline(catId,slot)", panels)
        settings = read("admin-exam-settings.js")
        self.assertIn("openSettings(catId, {embedded = false} = {})", settings)
        self.assertIn("if (!embedded) { await switchAdminSection('exam-settings', true)", settings)
        workspace = read("admin-workspace.js")
        self.assertIn("!actions.closest('[data-exam-embedded]')", workspace)


class MaterialAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.js = read("admin-course-material.js")

    def test_each_material_says_course_and_audience(self):
        self.assertIn("📘 屬於課程：", self.js)
        self.assertIn("📁 尚未歸入課程", self.js)
        self.assertIn("👁 誰能看：🔒 本組限定", self.js)
        self.assertIn("👁 誰能看：🌐 全科共用", self.js)
        self.assertIn("👁 誰能看：👥 指定組別", self.js)

    def test_ai_authoring_enters_from_course(self):
        self.assertIn("data-course-ai-authoring=", self.js)
        self.assertIn("openTeacherCourseEditWorkspace(courseId,2)", self.js)

    def test_narration_badge_and_remove(self):
        self.assertIn("🎧 附配音", self.js)
        self.assertIn("data-material-narration-remove=", self.js)
        self.assertIn("移除配音", self.js)
        self.assertIn("method:'DELETE'", self.js)


class PgyLearnerPanelTests(unittest.TestCase):
    def test_panel_says_pgy_and_collapses_when_empty(self):
        js = read("teacher-learners-p2.js")
        self.assertIn("（PGY 指派）", js)
        self.assertIn("目前沒有 PGY 指派給你的學員", js)
        self.assertIn("內部教育訓練", js)
        self.assertIn("section.dataset.p2Empty='1'", js)
        self.assertNotIn("只顯示伺服器判定你可查看的學員", js)


if __name__ == "__main__":
    unittest.main()
