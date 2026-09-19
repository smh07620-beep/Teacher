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
        for token in ('mixed_all','mixed_choice_multi','video_mixed','[自訂題型配置]','data-mix-type=\"${t}\"',"['choice','單選',4]","['essay','問答',2]"):
            self.assertIn(token, studio)
        self.assertNotIn("fetch('/api/ai-questions/generate'", studio)
        ai = ROOT.joinpath('static/admin-ai-questions.js').read_text(encoding='utf-8')
        self.assertIn("fetch('/api/ai-questions/generate'", ai)

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
