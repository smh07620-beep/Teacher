import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TrainingComplianceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "static" / "system.html").read_text(encoding="utf-8")
        cls.ui = (ROOT / "static" / "admin-compliance-91.js").read_text(encoding="utf-8")
        cls.router = (ROOT / "static" / "admin-workspace.js").read_text(encoding="utf-8")
        cls.rbac = (ROOT / "static" / "rbac-ui-681.js").read_text(encoding="utf-8")
        cls.assets = (ROOT / "teacher_app" / "frontend" / "assets.py").read_text(encoding="utf-8")
        cls.bootstrap = (ROOT / "static" / "system-bootstrap.js").read_text(encoding="utf-8")

    def test_workspace_nav_and_panel_exist(self):
        self.assertIn('id="admin-nav-compliance"', self.html)
        self.assertIn('id="admin-section-compliance"', self.html)
        self.assertIn('id="admin-compliance-body"', self.html)

    def test_ui_uses_read_only_compliance_endpoint(self):
        self.assertIn("/api/training-compliance?", self.ui)
        self.assertIn("credentials:'same-origin'", self.ui)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertNotIn(f"method:'{method}'", self.ui)

    def test_workspace_and_rbac_are_registered(self):
        self.assertIn("registerWorkspace('compliance'", self.ui)
        self.assertIn("compliance: ['training.compliance.read']", self.rbac)
        self.assertIn("'admin-nav-compliance': WORKSPACE_RULES.compliance", self.rbac)
        self.assertIn("compliance: {icon:'✅'", self.router)

    def test_asset_and_deep_link_are_registered(self):
        self.assertIn('"/admin-compliance-91.js"', self.assets)
        self.assertIn("'compliance'", self.bootstrap)

    def test_no_inline_event_handlers_added_to_new_panel(self):
        start = self.html.index('id="admin-section-compliance"')
        end = self.html.index('<!-- V5.4.0', start)
        panel = self.html[start:end].lower()
        self.assertNotIn(" onclick=", panel)
        self.assertNotIn(" onchange=", panel)
        self.assertNotIn(" oninput=", panel)


if __name__ == "__main__":
    unittest.main()
