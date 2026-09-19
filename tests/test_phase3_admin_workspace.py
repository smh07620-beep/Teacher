import unittest
from pathlib import Path

from flask import Flask

from pgy_frontend import ASSET_MANIFEST, register_pgy_frontend


ROOT = Path(__file__).parents[1]


class Phase3AdminWorkspaceRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = ROOT.joinpath('static/admin-workspace.js').read_text(encoding='utf-8')
        self.results_mode = ROOT.joinpath('static/admin-results-workspace.js').read_text(encoding='utf-8')

    def test_router_preserves_public_workspace_contracts(self):
        for name in (
            'normalizeAdminWorkspace',
            'paintAdminWorkspaceNav',
            'syncAdminSectionChrome',
            'switchAdminSection',
            'switchAdminWorkspace',
            'toggleAdminModal',
            'openAdminWorkspace',
            'openTeacherAssessment',
        ):
            self.assertIn(f'window.{name}', self.router)
        self.assertIn("name === 'courses' || name === 'materials'", self.router)
        self.assertIn("name === 'assessment' || name === 'questions'", self.router)
        self.assertIn("name === 'scoring' || name === 'pgy'", self.router)

    def test_router_loads_before_rbac_wrapper(self):
        ordered = dict(ASSET_MANIFEST["system"]["ordered"])["/system-admin.js"]
        self.assertLess(ordered.index('/admin-workspace.js'), ordered.index('/admin-results-workspace.js'))
        app = Flask(__name__)
        register_pgy_frontend(app)

        @app.get('/system')
        def system_page():
            return (
                '<html><body>'
                '<script defer src="/system-admin.js?v=6502"></script>'
                '<script defer src="/rbac-ui-681.js?v=6811"></script>'
                '</body></html>'
            )

        html = app.test_client().get('/system').get_data(as_text=True)
        self.assertLess(html.index('/system-admin.js?v='), html.index('/admin-workspace.js?v='))
        self.assertLess(html.index('/admin-workspace.js?v='), html.index('/admin-results-workspace.js?v='))
        self.assertLess(html.index('/admin-results-workspace.js?v='), html.index('/rbac-ui-681.js?v='))
        self.assertNotIn('/system-admin.js?v=6502', html)
        self.assertNotIn('/admin-workspace.js?v=7110', html)

    def test_teacher_and_results_use_extracted_mode_router(self):
        self.assertNotIn('const legacySwitchWorkspace = window.switchAdminWorkspace;', self.router)
        self.assertNotIn('window.__teacherAdminResultsWorkspace', self.router)
        self.assertIn("registerWorkspace('teacher', switchWorkspace)", self.results_mode)
        self.assertIn("registerWorkspace('results', switchWorkspace)", self.results_mode)
        self.assertNotIn('legacySwitchWorkspace(requested, force)', self.router)

    def test_section_cache_and_worker_probe_policy_are_preserved(self):
        self.assertIn('loaded: {content:false, quiz:false, word:false, pgy:false, results:false}', self.router)
        self.assertIn('if (!force && state.loaded[name]) return;', self.router)
        self.assertIn('Storage/worker probes remain intentionally deferred', self.router)
        self.assertNotIn('renderMaterialJobs(', self.router)

    def test_core_section_switch_hides_dynamic_extension_panels(self):
        self.assertIn("document.querySelectorAll('.admin-section-panel').forEach", self.router)
        self.assertIn("item.id !== sectionId", self.router)

    def test_workspace_state_and_nav_are_set_before_extension_dispatch(self):
        dispatch = self.router[self.router.index('async function switchWorkspace'):self.router.index('async function toggleCoreModal')]
        self.assertLess(dispatch.index('state.workspace = workspace'), dispatch.index('const extension ='))
        self.assertLess(dispatch.index('paintWorkspaceNav(workspace)'), dispatch.index('const extension ='))

    def test_router_does_not_redefine_rbac_or_profile_metadata_as_policy(self):
        for forbidden in (
            'professional_title',
            'responsibility_tags',
            'professionalTitle===',
            'responsibilityTags.includes',
            'localStorage.setItem',
            'sessionStorage.setItem',
            'canOpenWorkspace',
        ):
            self.assertNotIn(forbidden, self.router)


if __name__ == '__main__':
    unittest.main()
