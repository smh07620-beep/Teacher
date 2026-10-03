from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProductGoldenPathP1BrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin_workspace = (ROOT / "static" / "admin-workspace.js").read_text(encoding="utf-8")
        cls.browser_gp = (ROOT / "tests" / "playwright" / "product-golden-path-p1-real-flask.spec.js").read_text(encoding="utf-8")
        cls.teacher_workspace = (ROOT / "static" / "teacher-workspace-1014.js").read_text(encoding="utf-8")
        cls.people = (ROOT / "static" / "admin-people.js").read_text(encoding="utf-8")
        cls.roles_signing = (ROOT / "static" / "roles-signing-66.js").read_text(encoding="utf-8")

    def test_admin_modal_respects_requested_deep_link_workspace(self):
        self.assertIn(
            "const requestedWorkspace = new URLSearchParams(window.location.search).get('workspace');",
            self.admin_workspace,
        )
        self.assertIn(
            "requestedWorkspace || state.workspace || 'course-materials'",
            self.admin_workspace,
        )
        self.assertNotIn(
            "await window.switchAdminWorkspace?.('course-materials', false);",
            self.admin_workspace,
        )

    def test_workspace_url_stabilizes_before_async_renderer(self):
        resolved_at = self.admin_workspace.index("const extension = await resolveWorkspaceHandler(requested, workspace)")
        sync_at = self.admin_workspace.index("syncWorkspaceUrl(requested || workspace);")
        renderer_at = self.admin_workspace.index("await extension(context)")
        self.assertLess(resolved_at, sync_at)
        self.assertLess(sync_at, renderer_at)

    def test_multi_role_browser_gate_uses_canonical_rbac_profile(self):
        self.assertGreaterEqual(self.browser_gp.count("/api/auth/profile"), 2)
        self.assertNotIn("page.request.get(`${baseURL}/api/auth/me`)", self.browser_gp)


    def test_dual_role_switcher_reconciles_existing_container(self):
        self.assertIn("host.replaceChildren(...expected)", self.teacher_workspace)
        self.assertIn("setTimeout(ensurePersonaSwitcher, 0)", self.teacher_workspace)

    def test_people_workspace_can_recover_missing_create_panel(self):
        self.assertIn("function ensureAdminUserCreatePanel()", self.people)
        self.assertIn("if(existing)return existing", self.people)
        self.assertIn("ensureAdminUserCreatePanel();", self.people)

    def test_account_creation_has_one_owner_and_keeps_roles_with_profile_metadata(self):
        start = self.people.index("async function createAdminUserAccount()")
        end = self.people.index("function renderAdminActivitySummary", start)
        create = self.people[start:end]
        self.assertIn("role:mainRole", create)
        self.assertIn("roles,", create)
        self.assertIn("professionalTitle:", create)
        self.assertIn("responsibilityTags:", create)
        self.assertIn("const successMessage=", create)
        self.assertIn("window.createAdminUserAccount=createAdminUserAccount;", self.people)
        self.assertNotIn("window.createAdminUserAccount =", self.roles_signing)
        self.assertNotIn("__teacher66CreateWrapped", self.roles_signing)
        self.assertIn("window.TeacherRoleSigning66 = Object.freeze", self.roles_signing)
        self.assertIn("getCreateRoles", self.roles_signing)



if __name__ == "__main__":
    unittest.main()
