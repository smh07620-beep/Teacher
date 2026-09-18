import unittest
from pathlib import Path

from pgy_frontend import ASSET_MANIFEST

ROOT = Path(__file__).parents[1]


class Phase3AdminJobsTests(unittest.TestCase):
    def test_jobs_module_loads_after_question_bank_override(self):
        body = ASSET_MANIFEST["system"]["body"]
        question_pos = body.index('/admin-question-bank.js')
        jobs_pos = body.index('/admin-jobs.js')
        self.assertLess(question_pos, jobs_pos)

    def test_jobs_module_preserves_queue_global_contracts(self):
        source = ROOT.joinpath('static/admin-jobs.js').read_text(encoding='utf-8')
        for name in (
            'materialJobStatusLabel',
            'materialJobStatusClass',
            'scheduleMaterialJobsRefresh',
            'renderMaterialJobs',
            'retryMaterialJob',
            'cancelMaterialJob',
        ):
            self.assertIn(f'window.{name}', source)
        self.assertIn('/api/material-jobs?limit=20', source)
        self.assertIn('/retry', source)
        self.assertIn('/cancel', source)
        self.assertIn('X-Admin-Key', source)

    def test_jobs_module_keeps_refresh_state_private_and_security_boundary(self):
        source = ROOT.joinpath('static/admin-jobs.js').read_text(encoding='utf-8')
        self.assertIn('let materialJobsRefreshTimer = null;', source)
        self.assertIn('getAdminKey', source)
        self.assertNotIn('professional_title', source)
        self.assertNotIn('responsibility_tags', source)
        self.assertNotIn('localStorage.setItem', source)
        self.assertNotIn('sessionStorage.setItem', source)


if __name__ == '__main__':
    unittest.main()
