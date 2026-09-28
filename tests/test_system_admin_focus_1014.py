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

    def test_system_admin_nav_keeps_only_platform_governance(self):
        for label in (
            "👥 人員與權限",
            "📄 紙本文件範本",
            "⚙️ 系統與服務",
            "🖥️ Worker / Job 狀態",
            "🛡️ 備份維護",
            "🔎 稽核紀錄",
        ):
            self.assertIn(label, self.source)
        self.assertIn("navHost.replaceChildren(...groups)", self.source)

    def test_teaching_daily_work_is_not_reintroduced_into_system_nav(self):
        self.assertNotIn("教材與課程", self.source)
        self.assertNotIn("評量與出題", self.source)
        self.assertNotIn("成績管理", self.source)
        self.assertIn("日常教材、媒體、出題與紙本輸出已移至「教師工作區」", self.source)

    def test_multi_role_system_admin_can_escape_focus_via_teacher_persona(self):
        self.assertIn("params.get('persona') !== 'teacher'", self.source)

    def test_module_does_not_change_server_authorization(self):
        self.assertIn("has('system.manage')", self.source)
        for forbidden in ("ROLE_PERMISSIONS", "require_role", "require_permission", "X-Admin-Key"):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
