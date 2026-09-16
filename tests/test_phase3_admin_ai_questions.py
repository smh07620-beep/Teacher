import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class Phase3AdminAiQuestionsTests(unittest.TestCase):
    def test_module_loads_after_existing_phase3_overrides(self):
        frontend = ROOT.joinpath('pgy_frontend.py').read_text(encoding='utf-8')
        self.assertLess(frontend.index('/admin-material-upload.js?v=7108'), frontend.index('/admin-ai-questions.js?v=7109'))

    def test_ai_picker_generation_and_candidate_contracts_are_global(self):
        source = ROOT.joinpath('static/admin-ai-questions.js').read_text(encoding='utf-8')
        for name in ('loadAiMaterialOptions', 'toggleAiMaterialSelection', 'filterAiMaterials', 'recommendAiMaterials', 'adminGenerateAiQuestions', 'pollAiProgress', 'renderAiQuestionCandidates', 'collectAiCandidate', 'adminImportAiCandidates'):
            self.assertIn(f'window.{name}', source)
        for endpoint in ('/api/slides?area=', '/api/ai-questions/generate', '/api/slides/upload-progress/', '/api/ai-questions/import'):
            self.assertIn(endpoint, source)

    def test_ai_module_keeps_authorization_at_server_boundary(self):
        source = ROOT.joinpath('static/admin-ai-questions.js').read_text(encoding='utf-8')
        self.assertIn('getAdminKey', source)
        self.assertIn('X-Admin-Key', source)
        self.assertNotIn('professional_title', source)
        self.assertNotIn('responsibility_tags', source)
        self.assertNotIn('role ===', source)
        self.assertNotIn('role==', source)


if __name__ == '__main__':
    unittest.main()
