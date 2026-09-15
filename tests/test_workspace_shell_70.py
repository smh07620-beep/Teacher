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

    def test_maintenance_card_moves_out_of_generic_system_panel(self):
        self.assertIn("admin-section-maintenance", self.source)
        self.assertIn("teacher64-maintenance", self.source)
        self.assertIn("maintenancePanel.appendChild(card)", self.source)
        self.assertIn("has('backup.manage') || has('education.cross_group.manage')", self.source)

    def test_auditor_gets_a_dedicated_read_only_surface(self):
        for marker in (
            "roles.has('auditor')",
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
        self.assertNotIn("professionalTitle", self.source)
        self.assertNotIn("responsibilityTags", self.source)
        self.assertNotIn("professional_title", self.source)
        self.assertNotIn("responsibility_tags", self.source)

    def test_workspace_shell_is_loaded_after_maintenance_bridge(self):
        maintenance = self.frontend.index('/maintenance-64.js?v=6605')
        shell = self.frontend.index('/workspace-shell-70.js?v=7001')
        self.assertLess(maintenance, shell)
        self.assertIn('if "/workspace-shell-70.js" not in html', self.frontend)


if __name__ == "__main__":
    unittest.main()
