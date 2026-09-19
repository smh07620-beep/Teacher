import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class RcMobileWorkspaceStability75Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath('static/system.html').read_text(encoding='utf-8')
        cls.workspace = ROOT.joinpath('static/admin-workspace.js').read_text(encoding='utf-8')
        cls.studio = ROOT.joinpath('static/teacher-content-studio-71.js').read_text(encoding='utf-8')
        cls.bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')

    def test_legacy_material_executor_never_flashes_visible(self):
        self.assertRegex(self.html, r'id="admin-material-workspace" class="hidden [^"]+" aria-hidden="true"')
        self.assertNotIn("document.getElementById('admin-material-workspace')?.classList.remove('hidden')", self.workspace)
        self.assertIn("materialExecutor?.classList.add('hidden')", self.workspace)
        self.assertIn("materialExecutor?.setAttribute('aria-hidden', 'true')", self.workspace)
        self.assertIn('canonical upload executor stays mounted but is never promoted', self.workspace)

    def test_ai_authoring_stays_inside_unified_studio(self):
        self.assertIn('data-ai-question-studio="${c.id}"', self.bank)
        for marker in ('renderExamContainer', 'runExamAction', 'mountAiPanel', 'restoreAiPanel', 'data-teacher75-ai-host', 'const deadline=Date.now()+6000'):
            self.assertIn(marker, self.studio)
        self.assertIn("if(action==='ai')return mountAiPanel(catId);", self.studio)
        self.assertNotIn('chooseExamForAi', self.studio)
        self.assertNotIn("assessment681Tab?.('ai')", self.studio)
        self.assertIn('已鎖定目前考卷；關聯教材會自動帶入', self.studio)

    def test_modified_browser_javascript_syntax(self):
        for asset in ('admin-workspace.js', 'admin-question-bank.js', 'teacher-content-studio-71.js'):
            completed = subprocess.run(
                ['node', '--check', str(ROOT / 'static' / asset)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)


if __name__ == '__main__':
    unittest.main()
