from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ROUTER = (ROOT / "static" / "admin-workspace.js").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "static" / "system-bootstrap.js").read_text(encoding="utf-8")


class AdminPageModeBlankScreen1024Tests(unittest.TestCase):
    def test_admin_url_does_not_hide_the_page_before_workspace_open_succeeds(self):
        self.assertIn("syncPageModeClass(false);", ROUTER)
        self.assertIn("prevent", ROUTER)
        self.assertIn("typeof window.toggleAdminModal!=='function'", BOOTSTRAP)
        self.assertIn("document.body?.classList.remove('admin-page-mode')", BOOTSTRAP)

    def test_admin_url_waits_for_the_canonical_workspace_router(self):
        self.assertIn("attempt<20", BOOTSTRAP)
        self.assertIn("await window.toggleAdminModal(true)", BOOTSTRAP)
        self.assertIn("typeof window.switchAdminWorkspace==='function'", BOOTSTRAP)


if __name__ == "__main__":
    unittest.main()
