"""首頁「最近更新」要顯示教材真正所屬的組別（2026-10-13）。

學員端 /api/slides 會把「共用自其他組」的教材 group 改寫成使用者自己的組別，
真正的擁有組別放在 sharedFromGroup；首頁若直接用 group，就會永遠顯示成自己的組別。
"""
import unittest
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "static" / "portal-v56.js").read_text(encoding="utf-8")


class HomeLatestMaterialsRealGroupTests(unittest.TestCase):
    def test_label_and_link_use_the_owner_group(self):
        self.assertIn("const ownerGroup=m.sharedFromGroup||m.group;", SOURCE)
        self.assertIn("[ownerGroup]||'')", SOURCE)
        self.assertIn("encodeURIComponent(ownerGroup||'grpBio')", SOURCE)
        self.assertIn("（共用）", SOURCE)


if __name__ == "__main__":
    unittest.main()
