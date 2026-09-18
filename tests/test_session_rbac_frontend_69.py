import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class SessionRbacFrontend69Tests(unittest.TestCase):
    def source(self, name):
        return ROOT.joinpath("static", name).read_text(encoding="utf-8")

    def test_active_assessment_advanced_tools_use_session_rbac_without_admin_key(self):
        source = self.source("assessment-advanced-74.js")
        self.assertIn("credentials:'same-origin'", source)
        self.assertIn("登入已逾時，請重新登入", source)
        self.assertIn("此帳號沒有這項操作權限", source)
        self.assertNotIn("getAdminKey", source)
        self.assertNotIn("X-Admin-Key", source)

    def test_retired_assessment_compatibility_router_is_removed(self):
        self.assertFalse(ROOT.joinpath("static", "assessment-681.js").exists())

    def test_teaching_editor_uses_session_rbac_without_admin_key(self):
        source = self.source("teaching.js")
        self.assertIn("credentials:'same-origin'", source)
        self.assertNotIn("getAdminKey", source)
        self.assertNotIn("X-Admin-Key", source)

    def test_role_material_list_no_longer_sends_fake_header(self):
        source = self.source("rbac-ui-681.js")
        self.assertIn("credentials:'same-origin'", source)
        self.assertNotIn("'X-Admin-Key': 'rbac-session'", source)

    def test_sensitive_bridge_strips_legacy_fake_header_and_retries_428(self):
        source = self.source("sensitive-elevation-69.js")
        for marker in (
            "headers.get('X-Admin-Key') === 'rbac-session'",
            "headers.delete('X-Admin-Key')",
            "response.status !== 428",
            "contract.elevationRequired",
            "ensureElevation()",
            "15 分鐘內有效",
            "credentials:'same-origin'",
        ):
            self.assertIn(marker, source)

    def test_maintenance_explicitly_elevates_browser_download_and_restore(self):
        source = self.source("maintenance-64.js")
        self.assertIn("ensureSensitiveElevation69", source)
        self.assertIn("if(!(await ensureSensitive())) return;", source)
        self.assertIn("window.location.href='/api/maintenance/backup'", source)

    def test_sensitive_bridge_is_loaded_after_legacy_admin_bundle(self):
        html = self.source("system.html")
        legacy = '<script defer src="/system-admin.js?v=6502"></script>'
        bridge = '<script defer src="/sensitive-elevation-69.js?v=6900"></script>'
        self.assertIn(legacy, html)
        self.assertIn(bridge, html)
        self.assertLess(html.index(legacy), html.index(bridge))


if __name__ == "__main__":
    unittest.main()
