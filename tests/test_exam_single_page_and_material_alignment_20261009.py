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
        # 卡片上不再有獨立的「AI 製作」鈕；AI 製作在編輯課程第 2 步。
        self.assertNotIn("data-course-ai-authoring=", self.js)
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


class ReviewSourceEditorSimplifiedTests(unittest.TestCase):
    def test_teacher_sees_material_name_and_hint_only_by_default(self):
        js = read("review-links-66.js")
        self.assertIn("function materialSelect(selectedId)", js)
        self.assertIn("不指定教材", js)
        # 定位細節收進預設收合的選填區，欄位仍在，儲存時照常讀取。
        advanced = js[js.index('data-review-source-advanced-66="1"'):]
        for field in ("reviewAnchorType", "reviewPage", "reviewTimeSeconds", "reviewRegionHint", "reviewSection"):
            self.assertIn(f'data-field="{field}"', advanced)
        self.assertNotIn("<details open", js)
        self.assertNotIn("placeholder=\"選擇或輸入教材 ID\"", js)


class ExamPublishConsolidationTests(unittest.TestCase):
    def test_one_primary_action_and_visible_feedback(self):
        html = read("system.html")
        settings = read("admin-exam-settings.js")
        # 只剩一顆主按鈕；「完成審核」拿掉（發布時自動審核）。
        self.assertEqual(html.count('data-csp-click="examPrimaryAction()"'), 1)
        self.assertNotIn("✅ 完成審核", html)
        self.assertIn("window.examPrimaryAction = primaryAction", settings)
        self.assertIn("publish.textContent = published ? '💾 儲存變更' : '🚀 發布考卷'", settings)
        # 結果顯示在頁面上方固定橫幅，且發布成功講明「學員現在看得到」。
        self.assertIn("sticky top-2 z-30", settings)
        self.assertIn("已發布！學員現在看得到這份考卷", settings)
        self.assertIn("⏳ 處理中…", settings)

    def test_audience_is_one_block_and_advanced_options_are_collapsed(self):
        html = read("system.html")
        block = html[html.index('id="exam-advanced-settings"'):]
        for field in ("exam-settings-course", "exam-settings-audience", "exam-settings-desc", "exam-settings-blind", "exam-draw-all", "exam-quota-choice"):
            self.assertIn(f'id="{field}"', block)
        # 日常設定留在外面：名稱、誰能考、時間、及格標準。
        head = html[html.index('id="exam-settings-title"'):html.index('id="exam-advanced-settings"')]
        for field in ("exam-who-host", "exam-settings-opens-at", "exam-settings-closes-at", "exam-settings-passing-score"):
            self.assertIn(f'id="{field}"', head)

    def test_question_rows_do_not_each_carry_a_set_scope_button(self):
        js = read("content-audience-1014.js")
        self.assertIn("function questionAudienceControl(item, onClick)", js)
        self.assertIn("🌐 設定共用範圍", js)
        body = js[js.index("function decorateQuestions"):js.index("async function importSharedQuestion")]
        self.assertNotIn("audienceControl(item", body)

    def test_new_action_is_allowlisted(self):
        self.assertIn("'examPrimaryAction'", read("system-csp-actions.js"))


class QuestionInlineEditTests(unittest.TestCase):
    def setUp(self):
        self.ui = read("admin-question-editor-ui.js")

    def test_editing_one_question_closes_others_and_keeps_context(self):
        # 一次只展開一題；其他題目仍在上下方，底部固定列說明正在編輯第幾題。
        self.assertIn("if(open&&!bulkExpanding)", self.ui)
        self.assertIn("正在編輯第 ${rowNumber(open[0])||'?'} 題", self.ui)
        self.assertIn("其他題目在上方與下方", self.ui)
        self.assertIn("scrollIntoView({behavior:'smooth',block:'start'})", self.ui)

    def test_editor_is_compact_with_cancel_and_saved_feedback(self):
        self.assertIn('data-role="moreFields"', self.ui)
        more = self.ui[self.ui.index('data-role="moreFields"'):]
        for field in ('data-field="difficulty"', 'data-field="tag"', 'data-field="explanation"', 'data-field="active"'):
            self.assertIn(field, more)
        self.assertIn("adminCancelInlineQuestionEditor", self.ui)
        self.assertIn("window.flashQuestionRow", self.ui)
        actions = read("admin-question-actions.js")
        self.assertIn("window.flashQuestionRow?.(qId,catId,'✅ 已儲存')", actions)
        self.assertIn("'adminCancelInlineQuestionEditor'", read("system-csp-actions.js"))

    def test_bulk_edit_still_expands_many_at_once(self):
        self.assertIn("bulkExpanding=true;", self.ui)


class CourseOutcomesMergedTests(unittest.TestCase):
    def test_tracking_and_feedback_are_one_dialog_with_two_tabs(self):
        js = read("teacher-course-tracking-f2.js")
        self.assertIn("📊 學習成果", js)
        self.assertIn('data-tracking-tab="progress"', js)
        self.assertIn('data-tracking-tab="feedback"', js)
        hub = read("admin-course-material.js")
        self.assertNotIn("appendCourseFeedbackSummaryPanels", hub)
        self.assertNotIn("查看回饋彙總", hub)


class SingleAssignmentTests(unittest.TestCase):
    def test_wizard_assignment_is_the_only_one_and_on_by_default(self):
        wiz = read("course-wizard-681.js")
        self.assertIn("assignmentEnabled:true", wiz)
        self.assertIn("唯一的指派", wiz)
        self.assertIn("誰能考：和這門課的「學習指派」相同", wiz)
        self.assertNotIn("state.assignmentEnabled=false;state.assigneeType", wiz)

    def test_course_materials_do_not_carry_their_own_audience(self):
        js = read("admin-course-material.js")
        self.assertIn("誰能看：依課程指派", js)
        self.assertIn("m.courseId?''", js)

    def test_course_exam_hides_its_own_picker(self):
        js = read("admin-exam-settings.js")
        self.assertIn("function applyExamWhoMode(courseId, catId, area, group)", js)
        self.assertIn("data-exam-who-by-course", js)


class MaterialsManagedInsideEditCourseTests(unittest.TestCase):
    def test_edit_course_step_two_lists_course_materials_with_actions(self):
        wiz = read("course-wizard-681.js")
        self.assertIn("data-cw681-course-materials", wiz)
        self.assertIn("本課程的教材（在這裡管理）", wiz)
        for action in ("toggle", "unlink", "delete"):
            self.assertIn(f'data-cw-mat-action="{action}"', wiz)
        self.assertIn("function paintCourseMaterials()", wiz)

    def test_course_hub_rows_point_to_edit_course_instead_of_own_menu(self):
        hub = read("admin-course-material.js")
        self.assertIn("data-material-manage-hint", hub)
        self.assertNotIn("data-material-edit-course=\"", hub.split("function bindMaterialNarrationControls")[0] + hub.split("function paintAdminCourseMaterialHub")[1])
        self.assertNotIn("✨ AI 製作</button>", hub)

    def test_card_primary_buttons_are_edit_and_outcomes_only(self):
        conv = read("teacher-interface-convergence-1014.js")
        self.assertIn("👥 補指派學員", conv)
        self.assertNotIn("makeCardButton('學習指派'", conv)


class ExamDraftQueueScopeTests(unittest.TestCase):
    def test_queue_switches_to_the_exam_scope_before_opening(self):
        js = read("teacher-action-queue-1024.js")
        self.assertIn("async function openExamDraft(examId, ready, item)", js)
        self.assertIn("areaSelect.value = area", js)
        self.assertIn("openExamDraft(String(item.examId), item.status === 'exam_ready', item)", js)


if __name__ == "__main__":
    unittest.main()
