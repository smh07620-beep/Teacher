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
        for action in ('aiGoReviewQuestions', 'aiGoBackToExam'):
            self.assertIn(f'data-csp-click="{action}(', ai)
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
