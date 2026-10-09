"""2026-10-09: 投影片翻頁速度：縮圖不重建、多頁預載、伺服器背景預先轉下兩頁。"""
import tempfile
import time
import unittest
from pathlib import Path

from teacher_app.materials import delivery_routes

ROOT = Path(__file__).resolve().parents[1]


class SlideViewerClientSpeedTests(unittest.TestCase):
    def setUp(self):
        self.js = ROOT.joinpath("static", "system-learner.js").read_text(encoding="utf-8")

    def test_page_turn_does_not_rebuild_thumbnails(self):
        body = self.js[self.js.index("function goToSlidePage(i)"):self.js.index("function slideViewerPrev()")]
        self.assertNotIn("renderSlideThumbs()", body)
        opener = self.js[self.js.index("function openSlideViewer("):self.js.index("function openSlideViewer(") + 4500]
        self.assertIn("renderSlideThumbs();", opener)

    def test_prefetches_ahead_and_dedupes(self):
        self.assertIn("function prefetchAroundPresentationPage(page)", self.js)
        self.assertIn("prefetchPresentationPage(page+2)", self.js)
        self.assertIn("const slidePrefetched=new Set()", self.js)
        self.assertIn("prefetchImageUrl(images[i])", self.js)


@unittest.skipIf(delivery_routes.pymupdf is None, "pymupdf not installed")
class SlidePageServerWarmTests(unittest.TestCase):
    def test_following_pages_are_rendered_in_background(self):
        pymupdf = delivery_routes.pymupdf
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "deck.pdf"
            doc = pymupdf.open()
            for number in range(1, 5):
                page = doc.new_page(width=720, height=405)
                page.insert_text((72, 72), f"page {number}")
            doc.save(str(pdf))
            doc.close()
            cache = Path(tmp) / "cache"
            cache.mkdir()
            first = delivery_routes._page_cache_target(cache, 1, "s")
            self.assertTrue(delivery_routes._render_presentation_page(pdf, 1, first))
            self.assertGreater(first.stat().st_size, 0)
            self.assertFalse(delivery_routes._render_presentation_page(pdf, 9, delivery_routes._page_cache_target(cache, 9, "s")))
            delivery_routes._warm_following_pages(pdf, cache, "s", 1, 4)
            wanted = [delivery_routes._page_cache_target(cache, n, "s") for n in (2, 3)]
            deadline = time.time() + 20
            while time.time() < deadline and not all(path.exists() for path in wanted):
                time.sleep(0.1)
            self.assertTrue(all(path.exists() and path.stat().st_size > 0 for path in wanted))
            self.assertFalse(delivery_routes._page_cache_target(cache, 4, "s").exists())
            self.assertEqual(list(cache.glob(".render-*")), [])


if __name__ == "__main__":
    unittest.main()
