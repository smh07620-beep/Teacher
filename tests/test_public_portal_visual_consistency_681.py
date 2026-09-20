from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class PublicPortalVisualConsistency681Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = (STATIC / "index.html").read_text(encoding="utf-8")
        cls.internal = (STATIC / "area-internal.html").read_text(encoding="utf-8")
        cls.pgy = (STATIC / "area-pgy.html").read_text(encoding="utf-8")
        cls.css = (STATIC / "portal.css").read_text(encoding="utf-8")

    def test_realistic_lab_photo_is_the_shared_hero_asset(self):
        asset = STATIC / "assets" / "v681" / "lab-training-photo.jpg"
        self.assertTrue(asset.exists())
        self.assertGreater(asset.stat().st_size, 100_000)
        self.assertIn('/assets/v681/lab-training-photo.jpg', self.home)
        self.assertGreaterEqual(self.css.count("/assets/v681/lab-training-photo.jpg"), 2)

    def test_public_headers_follow_the_supplied_reference_context(self):
        home_header = self.home[self.home.index('<header class="v56-header">'):self.home.index('</header>')]
        internal_header = self.internal[self.internal.index('<header class="v56-header">'):self.internal.index('</header>')]
        pgy_header = self.pgy[self.pgy.index('<header class="v56-header">'):self.pgy.index('</header>')]
        self.assertIn('>首頁</a>', home_header)
        self.assertNotIn('>院內課程</a>', home_header)
        self.assertNotIn('>PGY</a>', home_header)
        self.assertIn('>首頁</a>', internal_header)
        self.assertIn('>院內課程</a>', internal_header)
        self.assertNotIn('>PGY</a>', internal_header)
        self.assertIn('>首頁</a>', pgy_header)
        self.assertIn('>PGY</a>', pgy_header)
        self.assertNotIn('>院內課程</a>', pgy_header)
        for header in (home_header, internal_header, pgy_header):
            self.assertNotIn('>考核</a>', header)

    def test_home_medium_width_switches_to_a_safe_single_column_hero(self):
        self.assertIn('@media(max-width:1080px)', self.css)
        self.assertIn('.phase3-home .phase3-home-hero-art{display:block;min-height:230px}', self.css)
        self.assertIn('min-width:0;padding:44px 30px 42px 46px', self.css)

    def test_pgy_landing_remains_learner_focused(self):
        self.assertIn('分階段課程', self.pgy)
        self.assertIn('臨床實務資源', self.pgy)
        self.assertIn('學習進度追蹤', self.pgy)
        self.assertIn('PGY 學習專區', self.pgy)
        self.assertIn('基礎訓練', self.pgy)
        self.assertIn('進階訓練', self.pgy)
        self.assertIn('專科深化', self.pgy)
        self.assertIn('評核與紀錄', self.pgy)
        self.assertNotIn('PGY 學習層級（教學管理）', self.pgy)
        self.assertNotIn('PGY 評核方式（教學管理）', self.pgy)


if __name__ == "__main__":
    unittest.main()
