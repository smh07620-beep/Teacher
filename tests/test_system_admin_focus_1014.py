from pathlib import Path
import unittest

from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class SystemAdminFocus1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "system-admin-focus-1014.js").read_text(encoding="utf-8")

    def test_asset_loads_after_worker_navigation_exists(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertIn("/system-admin-focus-1014.js", body)
        self.assertLess(body.index("/worker-status-70.js"), body.index("/system-admin-focus-1014.js"))

    def test_system_admin_focus_does_not_rebuild_canonical_navigation(self):
        self.assertIn("Structural system navigation is owned by workspace-shell-70.js", self.source)
        self.assertIn("TEACHER_OWNED_NAV_IDS", self.source)
        self.assertIn("function applySystemFocus()", self.source)
        self.assertNotIn("navHost.replaceChildren", self.source)
        self.assertNotIn("function navGroup", self.source)
        self.assertNotIn("📄 紙本文件範本", self.source)
        self.assertNotIn("正式文件治理", self.source)

    def test_paper_template_entry_is_owned_by_teacher_workspace(self):
        self.assertIn("'admin-nav-word'", self.source)
        self.assertIn("item.classList.add('hidden')", self.source)
        self.assertIn("params.get('workspace') !== 'word'", self.source)
        self.assertIn("url.searchParams.set('workspace', 'people')", self.source)
        self.assertIn("url.searchParams.set('persona', 'system')", self.source)
        self.assertIn("window.switchAdminWorkspace?.('people', true)", self.source)
        self.assertIn("紙本輸出與範本維護已移至「教師工作區」", self.source)

    def test_teaching_daily_work_is_not_reintroduced_into_system_nav(self):
        self.assertNotIn("教材與課程", self.source)
        self.assertNotIn("評量與出題", self.source)
        self.assertNotIn("成績管理", self.source)
        self.assertIn("日常教材、媒體、出題、紙本輸出與範本維護已移至「教師工作區」", self.source)

    def test_system_focus_is_mutually_exclusive_with_teacher_persona(self):
        self.assertIn("requestedPersona === 'system'", self.source)
        self.assertIn("legacySystemWorkspaces.has(requestedWorkspace)", self.source)
        self.assertNotIn("params.get('persona') !== 'teacher'", self.source)

    def test_module_does_not_change_server_authorization(self):
        self.assertIn("has('system.manage')", self.source)
        for forbidden in ("ROLE_PERMISSIONS", "require_role", "require_permission", "X-Admin-Key"):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
