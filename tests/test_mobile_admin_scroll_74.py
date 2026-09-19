import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_CSS = ROOT / "static" / "admin.css"


class MobileAdminScrollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = ADMIN_CSS.read_text(encoding="utf-8")

    def test_mobile_admin_modal_owns_scroll_above_bottom_nav(self):
        self.assertIn("@media (max-width: 820px)", self.css)
        self.assertIn("#admin-modal {", self.css)
        self.assertIn("z-index: 200 !important", self.css)
        self.assertIn("height: 100dvh !important", self.css)
        self.assertIn("overflow-y: auto !important", self.css)
        self.assertIn("-webkit-overflow-scrolling: touch", self.css)

    def test_mobile_admin_navigation_returns_to_single_column_groups(self):
        mobile = self.css.split("@media (max-width: 820px)", 1)[1]
        self.assertIn(".v580-admin-groups", mobile)
        self.assertIn("grid-template-columns: 1fr !important", mobile)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr)) !important", mobile)
        self.assertIn("writing-mode: horizontal-tb !important", mobile)

    def test_desktop_admin_navigation_is_compact_and_single_row(self):
        desktop = self.css.split("@media (min-width: 1100px)", 1)[1].split("@media (min-width: 821px)", 1)[0]
        self.assertIn("minmax(0, 2.4fr)", desktop)
        self.assertIn("minmax(190px, 1.15fr)", desktop)
        self.assertIn("grid-template-columns: repeat(5, minmax(0, 1fr))", desktop)
        self.assertIn("padding: 8px 14px", desktop)
        self.assertIn("min-height: 36px !important", self.css)

    def test_mobile_rbac_badge_cannot_become_sixth_fixed_nav_item(self):
        mobile = self.css.split("@media (max-width: 820px)", 1)[1]
        self.assertIn(".v56-system-mobile-nav #rbac-profile-badge", mobile)
        self.assertIn("display: none !important", mobile)

    def test_mobile_bottom_nav_accounts_for_safe_area(self):
        mobile = self.css.split("@media (max-width: 820px)", 1)[1]
        self.assertIn("env(safe-area-inset-bottom)", mobile)
        self.assertIn("height: calc(60px + env(safe-area-inset-bottom)) !important", mobile)


if __name__ == "__main__":
    unittest.main()
