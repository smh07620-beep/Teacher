from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AiAuthoringUxConvergence76Tests(unittest.TestCase):
    def test_ai_mount_has_stable_contract_and_bounded_retry(self):
        bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        studio = ROOT.joinpath('static/teacher-content-studio-71.js').read_text(encoding='utf-8')
        self.assertIn('data-ai-question-studio="${c.id}"', bank)
        self.assertIn('waitForAiSection76', studio)
        self.assertIn('data-ai-retry-76', studio)
        self.assertNotIn("assessment681Tab?.('ai')", studio)

    def test_ai_presets_and_custom_mix_are_orchestration_only(self):
        studio = ROOT.joinpath('static/teacher-content-studio-71.js').read_text(encoding='utf-8')
        for label in ('新人基礎考核','PGY 核心能力','案例判讀','品質管理／異常處理','進階組內訓練','圖片判讀','影片互動','自訂混搭'):
            self.assertIn(label, studio)
        for token in (
            'mixed_all', 'mixed_choice_multi', 'video_mixed', '[自訂題型配置]',
            'data-mix-type="${t}"', "['choice','單選',3]", "['true_false','是非',2]", "['essay','問答',2]",
        ):
            self.assertIn(token, studio)
        self.assertNotIn("fetch('/api/ai-questions/generate'", studio)
        ai = ROOT.joinpath('static/admin-ai-questions.js').read_text(encoding='utf-8')
        self.assertIn("fetch('/api/ai-questions/generate'", ai)

    def test_ai_candidates_support_same_core_question_types_as_manual_authoring(self):
        bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        ai = ROOT.joinpath('static/admin-ai-questions.js').read_text(encoding='utf-8')
        runtime = ROOT.joinpath('teacher_app/assessments/ai_runtime.py').read_text(encoding='utf-8')
        for token in ('choice', 'multi', 'true_false', 'fill', 'essay'):
            self.assertIn(token, bank)
            self.assertIn(token, ai)
            self.assertIn(token, runtime)
        self.assertIn('<option value="true_false">是非題</option>', bank)
        self.assertIn("options:['是','否']", ai)
        self.assertIn('"true_false": "全部產生是非題', runtime)
        self.assertIn('"choice|multi|true_false|fill|essay"', runtime)


    def test_ai_type_select_is_compact_and_still_backend_compatible(self):
        bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        runtime = ROOT.joinpath('teacher_app/assessments/ai_runtime.py').read_text(encoding='utf-8')
        start = bank.index('id="ai-type-${c.id}"')
        select = bank[start:bank.index('</select>', start)]
        values = [part.split('"', 1)[0] for part in select.split('<option value="')[1:]]
        self.assertEqual(
            values,
            ['mixed_all', 'mixed_choice_multi', 'mixed', 'choice', 'multi', 'true_false', 'fill', 'essay', 'video_mixed'],
        )
        for value in values:
            self.assertIn(f'"{value}"', runtime)

    def test_ai_import_leaves_a_way_back_to_review_and_exam(self):
        ai = ROOT.joinpath('static/admin-ai-questions.js').read_text(encoding='utf-8')
        panels = ROOT.joinpath('static/teacher-content-tool-panels-710.js').read_text(encoding='utf-8')
        csp = ROOT.joinpath('static/system-csp-actions.js').read_text(encoding='utf-8')
        self.assertIn('data-csp-click="aiGoBackToExam(', ai)
        self.assertNotIn('data-csp-click="aiGoReviewQuestions(', ai)  # 只保留一個「返回考卷」
        for action in ('aiGoReviewQuestions', 'aiGoBackToExam'):
            self.assertIn(f"window.{action}=", ai)
            self.assertIn(f"'{action}'", csp)
        self.assertIn('returnToExam\n  };', panels)

    def test_question_manager_targets_visible_panel_and_exam_list_is_compact(self):
        editor = ROOT.joinpath('static/admin-question-editor-ui.js').read_text(encoding='utf-8')
        actions = ROOT.joinpath('static/admin-question-actions.js').read_text(encoding='utf-8')
        bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        html = ROOT.joinpath('static/system.html').read_text(encoding='utf-8')
        # 題庫面板可能同時有兩份（隱藏的＋搬進工作畫面的），必須寫進看得見的那份。
        self.assertIn('window.pickQuestionEl', editor)
        self.assertIn("pick('qlist')", editor)
        self.assertNotIn('document.getElementById(`qlist-${catId}`)', editor)
        self.assertIn("pick('qlist')", actions)
        self.assertNotIn('document.getElementById(`qlist-${catId}`)', actions)
        # 「⋯」選單貼近畫面底部時往上展開，不用再往下捲。
        self.assertIn('data-quiz-overflow-78', bank)
        self.assertIn("'bottom-full'", bank)
        # 統計列併在標題下方（只出現一次），不再自成一整列。
        self.assertEqual(html.count('id="admin-quiz-overview"'), 1)
        self.assertLess(html.index('id="admin-quiz-overview"'), html.index('admin-page-heading-tools', html.index('id="admin-quiz-workspace"')))

    def test_ai_progress_is_visible_and_shows_wait_time(self):
        ai = ROOT.joinpath('static/admin-ai-questions.js').read_text(encoding='utf-8')
        # 進度條外框預設 hidden，挑選時要看父層是否可見，否則進度會寫到隱藏的那份。
        self.assertIn('el.parentElement?.getClientRects().length', ai)
        self.assertIn('排隊等待 AI 接手', ai)
        self.assertIn('已進行 ${fmtSec(sec)}', ai)
        self.assertIn('d.examReview', ai)
        bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        self.assertIn('id="ai-audience-${c.id}"', bank)
        self.assertIn('/api/content-audience/questions/', ai)

    def test_save_all_gives_visible_feedback_without_alert(self):
        actions = ROOT.joinpath('static/admin-question-actions.js').read_text(encoding='utf-8')
        bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        self.assertIn('id="qsticky-msg-${c.id}"', bank)
        self.assertIn('目前沒有正在編輯的題目', actions)
        self.assertNotIn("alert('請先勾選要儲存的題目。')", actions)

    def test_exam_card_has_direct_submit_for_review_and_selection_badge_uses_visible_copy(self):
        bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        csp = ROOT.joinpath('static/system-csp-actions.js').read_text(encoding='utf-8')
        editor = ROOT.joinpath('static/admin-question-editor-ui.js').read_text(encoding='utf-8')
        self.assertIn('adminQuickReviewExam', bank)
        self.assertIn('adminOpenExamPublish', bank)
        self.assertIn("'adminOpenExamPublish'", csp)
        self.assertIn("'adminQuickReviewExam'", csp)
        self.assertIn("pk('qselected')", editor)

    def test_manual_question_form_has_same_audience_choice(self):
        bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        actions = ROOT.joinpath('static/admin-question-actions.js').read_text(encoding='utf-8')
        self.assertIn('id="qform-${c.id}-audience"', bank)
        self.assertIn('qform-${catId}-audience', actions)
        self.assertIn('/api/content-audience/questions/', actions)

    def test_question_edit_boxes_use_visible_copy(self):
        editor = ROOT.joinpath('static/admin-question-editor-ui.js').read_text(encoding='utf-8')
        actions = ROOT.joinpath('static/admin-question-actions.js').read_text(encoding='utf-8')
        self.assertIn('window.pickQuestionEditBox', editor)
        self.assertNotIn('document.getElementById(`qedit-${qId}`)', editor)
        self.assertIn('pickQuestionEditBox(qId)', actions)
        self.assertIn("pickQuestionEl('qsticky-msg',catId)", actions)

    def test_repaint_never_leaves_a_second_copy_of_a_mounted_tool(self):
        panels = ROOT.joinpath('static/teacher-content-tool-panels-710.js').read_text(encoding='utf-8')
        bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        self.assertIn('function reconcileAfterPaint', panels)
        self.assertIn('reconcileAfterPaint,', panels)
        start = bank.index('window.paintAdminQuizCategories=')
        self.assertIn('reconcileAfterPaint', bank[start:bank.index('\n', start)])

    def test_mobile_question_actions_are_collapsed(self):
        editor = ROOT.joinpath('static/admin-question-editor-ui.js').read_text(encoding='utf-8')
        bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        self.assertIn('flex flex-col sm:flex-row', editor)
        self.assertIn('aria-label="更多題目操作"', editor)
        self.assertIn('✏️ 編輯', editor)
        self.assertIn('qbulk-actions-${c.id}', bank)
        self.assertIn('勾選題目後顯示批次操作', bank)
        self.assertIn("classList.toggle('hidden',selected.length===0)", editor)
        self.assertNotIn('📝 全選編輯', bank)

    def test_bulk_question_mutations_use_batch_endpoint(self):
        actions = ROOT.joinpath('static/admin-question-actions.js').read_text(encoding='utf-8')
        self.assertIn("fetch('/api/quiz-questions/batch'", actions)
        self.assertIn('window.adminBulkSetQuestionTag = window.adminBulkTagQuestions', actions)
        self.assertNotIn("for(const id of ids){\n        const r=await fetch(`/api/quiz-questions/${encodeURIComponent(id)}`", actions)


if __name__ == '__main__':
    unittest.main()


class CoursePublishAutoExamTests(unittest.TestCase):
    @staticmethod
    def _read(name):
        from pathlib import Path
        return (Path(__file__).resolve().parents[1] / "static" / name).read_text(encoding="utf-8")

    def test_course_publish_auto_publishes_linked_exams(self):
        js = self._read("course-wizard-681.js")
        self.assertIn("async function autoPublishCourseExams", js)
        self.assertIn("COURSE_EXAM_UNPUBLISHED", js)
        self.assertIn("examOnlyBlocked", js)
        self.assertIn("/publish`,'POST'", js)
        # 本地時間必須先轉成 UTC，否則伺服器會當成 UTC 而差 8 小時。
        self.assertIn("toISOString()", js)

    def test_wizard_step_three_holds_exam_settings(self):
        js = self._read("course-wizard-681.js")
        self.assertIn("function examSettingsPanel", js)
        self.assertIn("saveWizardExamSettings", js)
        self.assertIn("courseWizard681SetExamField", self._read("system-csp-actions.js"))

    def test_exam_settings_page_is_simplified_and_blank_time_is_unlimited(self):
        js = self._read("admin-exam-settings.js")
        self.assertIn("function toUtcIso", js)
        self.assertNotIn("開始時間未設定", js)
        self.assertNotIn("最後考核日期未設定", js)
        self.assertIn("/review`", js)  # 發布時自動審核
        html = self._read("system.html")
        self.assertIn('id="exam-reviewer-name" type="hidden"', html)
        self.assertIn("留白＝不限制", html)


class TeacherTodoLinksTests(unittest.TestCase):
    def test_exam_drafts_appear_in_teacher_todo_with_exam_link(self):
        from teacher_app.notifications import events

        href = events._href({"examId": "cat-1", "area": "internal", "group": "grpBio", "persona": "teacher", "kind": "draft"})
        self.assertIn("workspace=assessment", href)
        self.assertIn("examId=cat-1", href)

    def test_teacher_review_link_goes_to_teacher_workspace_not_learner_exam_page(self):
        from teacher_app.notifications import events

        href = events._href({"kind": "review", "persona": "teacher", "resourceId": "rec-9", "area": "internal", "group": "grpBio", "target": "assessment"})
        self.assertIn("workspace=teacher", href)
        self.assertNotIn("module=exam", href)
        self.assertIn("recordId=rec-9", href)


class NoDuplicateStaticIdsTests(unittest.TestCase):
    def test_system_html_has_no_duplicate_ids(self):
        import collections
        import re
        from pathlib import Path

        html = (Path(__file__).resolve().parents[1] / "static" / "system.html").read_text(encoding="utf-8")
        ids = re.findall(r'\sid="([^"$]+)"', html)
        duplicates = [key for key, count in collections.Counter(ids).items() if count > 1]
        self.assertEqual(duplicates, [])


class ExamWhoCanUseUiTests(unittest.TestCase):
    @staticmethod
    def _read(name):
        from pathlib import Path
        return (Path(__file__).resolve().parents[1] / "static" / name).read_text(encoding="utf-8")

    def test_settings_page_and_wizard_share_one_assignee_picker(self):
        settings = self._read("admin-exam-settings.js")
        wizard = self._read("course-wizard-681.js")
        html = self._read("system.html")
        self.assertIn("window.ExamAssigneePicker", settings)
        self.assertIn("/assignees", settings)
        self.assertIn('id="exam-who-host"', html)
        self.assertIn("cw681-who-host", wizard)
        self.assertIn("ExamAssigneePicker.saveModel", wizard)
        # 設定頁儲存時一併送出名單（伺服器強制檢查）。
        self.assertIn("ExamAssigneePicker?.saveFor", settings)


class WizardFinishAfterPublishTests(unittest.TestCase):
    def test_wizard_leaves_after_publish_and_hides_save_draft(self):
        from pathlib import Path

        js = (Path(__file__).resolve().parents[1] / "static" / "course-wizard-681.js").read_text(encoding="utf-8")
        # publicationBusy 必須在離開精靈前放開，否則 openCourseWorkspace 會直接返回。
        self.assertIn("state.publicationBusy=false;\n    await openCourseWorkspace();", js)
        self.assertIn("finish.classList.toggle('hidden',isPublished)", js)
        self.assertIn("function examAuthoringBox", js)
        self.assertIn("state.openingAuthoring", js)
