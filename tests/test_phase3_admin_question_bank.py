import unittest
from pathlib import Path

from pgy_frontend import ASSET_MANIFEST

ROOT = Path(__file__).parents[1]


class Phase3AdminQuestionBankTests(unittest.TestCase):
    def test_question_bank_module_loads_after_materials_override(self):
        body = ASSET_MANIFEST["system"]["body"]
        materials_pos = body.index('/admin-materials.js')
        question_pos = body.index('/admin-question-bank.js')
        self.assertLess(materials_pos, question_pos)

    def test_question_bank_module_preserves_global_contracts(self):
        source = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        for name in (
            'groupOptionsForArea',
            'populateAdminGroupSelects',
            'onAdminMaterialGroupChange',
            'refreshAdminMaterialCategoryOptions',
            'onAdminQuizGroupChange',
            'paintAdminQuizCategories',
            'optimisticInsertQuizCategory',
            'patchVisibleQuizCounts',
            'renderAdminQuizCategories',
        ):
            self.assertIn(f'window.{name}', source)
        self.assertIn('/api/quiz-categories?group=', source)
        self.assertIn('/api/quiz-categories/admin?group=', source)
        self.assertNotIn('X-Admin-Key', source)

    def test_question_bank_module_keeps_existing_rbac_boundary(self):
        source = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        self.assertNotIn('getAdminKey', source)
        self.assertNotIn('professional_title', source)
        self.assertNotIn('responsibility_tags', source)
        self.assertNotIn('localStorage.setItem', source)
        self.assertNotIn('sessionStorage.setItem', source)


if __name__ == '__main__':
    unittest.main()
