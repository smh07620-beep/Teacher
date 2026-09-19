import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AdminFullPageWorkspace681Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath("static", "system.html").read_text(encoding="utf-8")
        cls.css = ROOT.joinpath("static", "admin.css").read_text(encoding="utf-8")
        cls.router = ROOT.joinpath("static", "admin-workspace.js").read_text(encoding="utf-8")
        cls.bootstrap = ROOT.joinpath("static", "system-bootstrap.js").read_text(encoding="utf-8")

    def test_workspace_has_full_page_shell_landmarks(self):
        for marker in (
            'class="admin-workspace-shell',
            'id="admin-workspace-header"',
            'id="admin-workspace-title"',
            'id="admin-workspace-content"',
            'id="admin-workspace-footer"',
            '← 返回教學首頁',
        ):
            self.assertIn(marker, self.html)

    def test_staff_entries_use_page_workspace_navigation(self):
        self.assertIn('data-csp-click="openTeachingMaterials()"', self.html)
        self.assertIn("window.location.assign(workspaceUrl(name || 'course-materials'))", self.router)
        self.assertIn("url.searchParams.set(PAGE_MODE_PARAM, '1')", self.router)
        self.assertIn("url.searchParams.set('workspace'", self.router)

    def test_page_mode_preserves_canonical_admin_dom_and_expands_it(self):
        self.assertIn("body.admin-page-mode #admin-modal", self.css)
        self.assertIn("grid-template-columns: 248px minmax(0, 1fr)", self.css)
        self.assertIn("max-width: 1800px !important", self.css)
        self.assertIn("body.admin-page-mode .v580-admin-groups", self.css)
        self.assertIn("body.admin-page-mode #admin-workspace-content", self.css)

    def test_closing_page_mode_returns_to_learning_url_without_admin_query(self):
        self.assertIn("url.searchParams.delete(PAGE_MODE_PARAM)", self.router)
        self.assertIn("url.searchParams.delete('workspace')", self.router)
        self.assertIn("window.location.assign(learningUrl())", self.router)

    def test_bootstrap_can_restore_extension_workspaces_from_url(self):
        for workspace in ("maintenance", "audit", "worker"):
            self.assertIn(f"'{workspace}'", self.bootstrap)


if __name__ == "__main__":
    unittest.main()
