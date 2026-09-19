import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class FinalUiRuntimeCleanup72Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.studio = ROOT.joinpath('static', 'teacher-content-studio-71.js').read_text(encoding='utf-8')
        cls.system_admin = ROOT.joinpath('static', 'system-admin.js').read_text(encoding='utf-8')
        cls.course_wizard = ROOT.joinpath('static', 'course-wizard-681.js').read_text(encoding='utf-8')

    def test_material_creation_has_one_visible_entry(self):
        for marker in (
            'consolidateMaterialWorkspace',
            'admin-material-workspace',
            'teacher72MaterialExecutor',
            'teacher75MaterialExecutorRoot',
            "root.classList.add('hidden')",
            "root.setAttribute('aria-hidden','true')",
        ):
            self.assertIn(marker, self.studio)
        self.assertNotIn('教材處理與背景工作', self.studio)
        self.assertNotIn('建立入口已統一', self.studio)
        # Executor controls stay in the DOM for canonical upload code; cleanup is
        # presentation-only and must not disable or delete them.
        self.assertIn('admin-pptx-upload-input', self.studio)
        self.assertIn('admin-upload-btn', self.studio)
        self.assertNotIn('node.disabled=true', self.studio.replace(' ', ''))

    def test_course_wizard_runtime_owner_stays_extracted(self):
        self.assertIn('course-wizard-681', self.course_wizard)
        self.assertIn('window.courseWizard681Create', self.course_wizard)
        self.assertNotIn('window.courseWizard681Create', self.system_admin)
        self.assertNotIn('course-wizard-681', self.system_admin)

    def test_session_rbac_no_longer_needs_admin_key_compatibility_glue(self):
        self.assertNotIn('getAdminKey', self.system_admin)
        self.assertNotIn('X-Admin-Key', self.system_admin)
        self.assertNotIn('rbac-session', self.system_admin)

    def test_studio_javascript_syntax(self):
        completed = subprocess.run(
            ['node', '--check', str(ROOT / 'static' / 'teacher-content-studio-71.js')],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)


if __name__ == '__main__':
    unittest.main()
