import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class AiAuthoringUxConvergence77Tests(unittest.TestCase):
    def test_exam_linked_materials_are_auto_selected_with_three_item_default(self):
        js=(ROOT/'static/admin-ai-questions.js').read_text(encoding='utf-8')
        for token in ('autoSelectLinkedAiMaterials','m.category===id','slice(0,3)','autoLinked=true','一次最多選 4 份教材'):
            self.assertIn(token,js)

    def test_studio_compacts_material_picker_and_duplicate_controls(self):
        js=(ROOT/'static/teacher-content-studio-71.js').read_text(encoding='utf-8')
        for token in ('data-ai-material-summary-77','依所選考卷自動帶入最多 3 份關聯教材','調整教材','data-ai-advanced-77','進階設定（題型／難度／題數／策略／出題重點）'):
            self.assertIn(token,js)

    def test_ai_prepare_flow_has_fast_path_and_global_deadline(self):
        js=(ROOT/'static/teacher-content-studio-71.js').read_text(encoding='utf-8')
        self.assertIn('AI_PREPARE_DEADLINE_77 = 6000',js)
        self.assertIn('let panel=document.getElementById(`qpanel-${catId}`)',js)
        self.assertIn('if(!panel){',js)
        self.assertIn('withTimeout77',js)
        self.assertIn('正在掛載 AI 出題工作室',js)
        self.assertIn('重新嘗試',js)

if __name__=='__main__':
    unittest.main()
