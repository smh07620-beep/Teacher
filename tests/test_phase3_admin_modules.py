import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class Phase3AdminModuleSplitTests(unittest.TestCase):
    def test_results_module_is_loaded_as_phase3_override(self):
        frontend = ROOT.joinpath('pgy_frontend.py').read_text(encoding='utf-8')
        self.assertIn('/admin-results.js?v=7100', frontend)
        self.assertIn('/system-admin.js', ROOT.joinpath('static/system.html').read_text(encoding='utf-8'))

    def test_results_module_preserves_legacy_global_contracts(self):
        source = ROOT.joinpath('static/admin-results.js').read_text(encoding='utf-8')
        for name in ('openEssayReview', 'closeEssayReview', 'submitEssayReview'):
            self.assertIn(f'window.{name}', source)
        self.assertIn('/api/records/${encodeURIComponent(r.id)}/review', source)
        self.assertIn('X-Admin-Key', source)
        self.assertIn('renderAdminTable', source)

    def test_results_module_keeps_review_state_private(self):
        source = ROOT.joinpath('static/admin-results.js').read_text(encoding='utf-8')
        self.assertIn("'use strict'", source)
        self.assertIn('let currentReviewRecordIndex = null;', source)


if __name__ == '__main__':
    unittest.main()
