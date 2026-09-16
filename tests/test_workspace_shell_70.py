"""Teacher 7.0 M2 role-specific administration workspace regressions."""
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class WorkspaceShell70Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT.joinpath("static", "workspace-shell-70.js").read_text(encoding="utf-8")
        cls.frontend = ROOT.joinpath("pgy_frontend.py").read_text(encoding="utf-8")

    def test_system_admin_is_split_into_focused_subworkspaces(self):
        for marker in (
            "navGroup('教學管理'",
            "navGroup('人員與權限'",
            "navGroup('系統與儲存'",
            "navGroup('備份維護'",
            "navGroup('安全與稽核'",
            "admin-nav-maintenance",
            "admin-nav-audit",
        ):
            self.assertIn(marker, self.source)

    def test_multirole_accounts_follow_one_canonical_surface(self):
        self.assertIn("const surfaceKey = String(R.surface?.key", self.source)
        self.assertIn("roles.has('system_admin') ? 'system'", self.source)
        self.assertIn("roles.has('education_admin') || has('education.cross_group.manage') ? 'education'", self.source)
        self.assertIn("roles.has('group_leader') || roles.has('clinical_teacher') ? 'teacher'", self.source)
        self.assertIn("roles.has('auditor') ? 'audit' : 'learner'", self.source)
        self.assertIn("const isSystemAdmin = surfaceKey === 'system'", self.source)
        self.assertIn("const isEducationAdmin = surfaceKey === 'education'", self.source)
        self.assertIn("const isAuditor = surfaceKey === 'audit'", self.source)
        # An auxiliary auditor role must not override a higher-precedence
        # system/education/teacher presentation surface.
        auth_block = self.source[self.source.index("const surfaceKey"):self.source.index("const workspaceHost")]
        self.assertNotIn("const isAuditor = roles.has('auditor')", auth_block)

    def test_maintenance_card_moves_out_of_generic_system_panel(self):
        self.assertIn("admin-section-maintenance", self.source)
        self.assertIn("teacher64-maintenance", self.source)
        self.assertIn("maintenancePanel.appendChild(card)", self.source)
        self.assertIn("has('backup.manage') || has('education.cross_group.manage')", self.source)

    def test_auditor_gets_a_dedicated_read_only_surface(self):
        for marker in (
            "surfaceKey === 'audit'",
            "admin-section-audit",
            "'/api/pgy/audit'",
            "唯讀稽核資料",
            "不提供新增、修改、發布或刪除操作",
            "navHost.replaceChildren(navGroup('稽核／唯讀'",
        ):
            self.assertIn(marker, self.source)
        # The dedicated audit loader is GET-only and never sends a mutation method.
        audit_block = self.source[self.source.index("async function renderAudit"):self.source.index("const previousSwitch")]
        self.assertNotIn("method:", audit_block)

    def test_auditor_entry_does_not_unlock_teacher_panels(self):
        self.assertIn("navHost.replaceChildren(navGroup('稽核／唯讀'", self.source)
        self.assertIn("document.querySelectorAll('.admin-section-panel').forEach", self.source)
        self.assertIn("window.switchAdminWorkspace('audit', true)", self.source)
        # Profile metadata may be documented in comments, but must never take part
        # in the actual role/capability calculation block.
        auth_block = self.source[self.source.index("const roles"):self.source.index("const workspaceHost")]
        self.assertNotIn("professionalTitle", auth_block)
        self.assertNotIn("responsibilityTags", auth_block)
        self.assertNotIn("professional_title", auth_block)
        self.assertNotIn("responsibility_tags", auth_block)

    def test_workspace_shell_is_loaded_after_maintenance_bridge(self):
        maintenance = self.frontend.index('/maintenance-64.js?v=6605')
        shell = self.frontend.index('/workspace-shell-70.js?v=7114')
        self.assertLess(maintenance, shell)
        self.assertIn('if "/workspace-shell-70.js" not in html', self.frontend)


if __name__ == "__main__":
    unittest.main()
