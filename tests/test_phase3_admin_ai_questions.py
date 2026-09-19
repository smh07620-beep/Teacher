import unittest
from pathlib import Path

from pgy_frontend import ASSET_MANIFEST

ROOT = Path(__file__).parents[1]


class Phase3AdminAiQuestionsTests(unittest.TestCase):
    def test_module_loads_after_existing_phase3_overrides(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertLess(body.index('/admin-material-upload.js'), body.index('/admin-ai-questions.js'))

    def test_ai_picker_generation_and_candidate_contracts_are_global(self):
        source = ROOT.joinpath('static/admin-ai-questions.js').read_text(encoding='utf-8')
        for name in ('loadAiMaterialOptions', 'toggleAiMaterialSelection', 'filterAiMaterials', 'recommendAiMaterials', 'adminGenerateAiQuestions', 'pollAiProgress', 'renderAiQuestionCandidates', 'collectAiCandidate', 'adminImportAiCandidates'):
            self.assertIn(f'window.{name}', source)
        for endpoint in ('/api/slides?area=', '/api/ai-questions/generate', '/api/ai-questions/jobs/', '/api/ai-questions/import'):
            self.assertIn(endpoint, source)

    def test_ai_module_keeps_authorization_at_server_boundary(self):
        source = ROOT.joinpath('static/admin-ai-questions.js').read_text(encoding='utf-8')
        self.assertNotIn('getAdminKey', source)
        self.assertNotIn('X-Admin-Key', source)
        self.assertNotIn('/api/slides/upload-progress/', source)
        self.assertIn('待審核題庫', source)
        self.assertNotIn('professional_title', source)
        self.assertNotIn('responsibility_tags', source)
        self.assertNotIn('role ===', source)
        self.assertNotIn('role==', source)


if __name__ == '__main__':
    unittest.main()
