import os
import unittest
from pathlib import Path
from unittest.mock import patch

from pgy_frontend import ASSET_MANIFEST, _apply_asset_manifest, _rewrite_local_asset_versions


ROOT = Path(__file__).parents[1]


class FrontendConvergence75Tests(unittest.TestCase):
    def source(self, name):
        return ROOT.joinpath("static", name).read_text(encoding="utf-8")

    def test_manifest_injects_one_ordered_admin_runtime(self):
        source = '<html><head></head><body><script defer src="/shared-core.js?v=old"></script><script defer src="/system-admin.js?v=old"></script></body></html>'
        html = _apply_asset_manifest(source, "system")
        for path in dict(ASSET_MANIFEST["system"]["ordered"])["/system-admin.js"]:
            self.assertEqual(html.count(f'src="{path}"'), 1)
        self.assertLess(html.index('src="/admin-results-data.js"'), html.index('src="/admin-results-workspace.js"'))
        self.assertNotIn('src="/admin-compat-facade.js"', html)

    def test_runtime_build_hash_replaces_all_local_asset_versions(self):
        with patch.dict(os.environ, {"ASSET_VERSION": "build-abc123"}, clear=False):
            html = _rewrite_local_asset_versions('<script src="/a.js?v=old"></script><link href="/b.css">')
        self.assertIn('/a.js?v=build-abc123', html)
        self.assertIn('/b.css?v=build-abc123', html)
        self.assertNotIn('?v=old', html)

    def test_css_runtime_is_converged_to_canonical_files(self):
        retired = (
            "phase3.css", "learner-layout-stability-73.css", "pgy-workflow.css",
            "portal-v56.css", "portal-v571.css", "v561.css", "v573.css",
            "v574.css", "v575.css", "v580.css",
        )
        for name in retired:
            self.assertFalse(ROOT.joinpath("static", name).exists(), name)
        self.assertIn(".phase3-home", self.source("portal.css"))
        self.assertIn("#learning-start", self.source("learner.css"))
        self.assertIn(".pgywf-shell", self.source("learner.css"))

    def test_api_client_is_the_only_fetch_assignment_owner(self):
        owners = []
        for path in ROOT.joinpath("static").glob("*.js"):
            source = path.read_text(encoding="utf-8").replace(" ", "")
            if "window.fetch=" in source or "global.fetch=" in source:
                owners.append(path.name)
        self.assertEqual(owners, ["api-client.js"])
        api = self.source("api-client.js")
        self.assertIn("global.fetch = fetchWithMiddleware", api)
        self.assertIn("middlewareNames", api)

    def test_fetch_features_register_middleware_in_semantic_order(self):
        latency = self.source("teacher-content-latency-712.js")
        review = self.source("review-links-66.js")
        elevation = self.source("sensitive-elevation-69.js")
        self.assertIn("apiClient?.use('teacher-content-latency-712',latencyMiddleware,100)", latency)
        self.assertIn("'review-source-66'", review)
        self.assertIn("200", review)
        self.assertIn("apiClient?.use('sensitive-elevation-69', elevationMiddleware, 300)", elevation)
        for source in (latency, review, elevation):
            self.assertNotIn("window.fetch =", source)

    def test_studio_actions_use_registry_and_retired_facade_is_removed(self):
        studio = self.source("teacher-content-studio-71.js")
        tools = self.source("teacher-content-tool-panels-710.js")
        latency = self.source("teacher-content-latency-712.js")
        self.assertEqual(studio.count("window.teacherContentStudioExamAction="), 1)
        self.assertIn("registerExamActions", studio)
        self.assertIn("registerExamActions", tools)
        self.assertIn("registerExamActions", latency)
        self.assertNotIn("teacherContentStudioExamAction=", tools)
        self.assertNotIn("teacherContentStudioExamAction=", latency)
        self.assertFalse(ROOT.joinpath("static", "admin-compat-facade.js").exists())

    def test_convergence_owns_question_next_click(self):
        composer = self.source("teacher-content-composer-72.js")
        convergence = self.source("teacher-ux-convergence-72.js")
        self.assertNotIn("event.target.closest('[data-composer-question-next]')", composer)
        self.assertNotIn("function openQuestionEditor", composer)
        self.assertIn("event.target.closest('[data-composer-question-next]')", convergence)

    def test_admin_workspace_router_has_one_global_owner(self):
        core = self.source("admin-workspace.js")
        rbac = self.source("rbac-ui-681.js")
        shell = self.source("workspace-shell-70.js")
        worker = self.source("worker-status-70.js")
        self.assertIn("window.AdminWorkspaceShell = Object.freeze", core)
        self.assertEqual(core.count("window.switchAdminWorkspace ="), 1)
        self.assertEqual(core.count("window.toggleAdminModal ="), 1)
        for source in (rbac, shell, worker):
            self.assertNotIn("window.switchAdminWorkspace =", source)
            self.assertNotIn("window.toggleAdminModal =", source)
        self.assertIn("addWorkspaceGuard", rbac)
        self.assertIn("EXTENSION_WORKSPACE_RULES", rbac)
        self.assertIn("audit: ['audit.read','audit.view']", rbac)
        self.assertIn("worker: ['system.manage']", rbac)
        self.assertIn("registerWorkspace('audit'", shell)
        self.assertIn("registerWorkspace('worker'", worker)
        self.assertNotIn("legacyPopulateGroups", rbac)
        self.assertNotIn("window.populateAdminGroupSelects =", rbac)

        guard = core.index("for (const guard of workspaceGuards)")
        extension = core.index("const extension = workspaceHandlers.get")
        after = core.index("for (const hook of afterWorkspaceHooks)")
        self.assertLess(guard, extension)
        self.assertLess(extension, after)

        modal_guard = core.index("for (const guard of modalGuards)")
        modal_override = core.index("for (const override of modalOpenOverrides)")
        self.assertLess(modal_guard, modal_override)


if __name__ == "__main__":
    unittest.main()
