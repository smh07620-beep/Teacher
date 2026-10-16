import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MediumSlideTests(unittest.TestCase):
    def _runtime_class(self):
        import teacher_app.storage.worker_runtime as module

        return next(v for v in vars(module).values() if isinstance(v, type) and hasattr(v, "make_medium_slide"))

    def test_large_slide_gets_1280_webp_and_small_slide_does_not(self):
        from PIL import Image

        cls = self._runtime_class()
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            Image.effect_noise((2400, 1350), 40).convert("RGB").save(folder / "slide-01.png")
            Image.new("RGB", (800, 450), "blue").save(folder / "slide-02.png")
            big = cls.make_medium_slide(folder / "slide-01.png", 1)
            small = cls.make_medium_slide(folder / "slide-02.png", 2)
            self.assertEqual(big.name, "slide-01.m.webp")
            self.assertEqual(Image.open(big).size, (1280, 720))
            self.assertLess(big.stat().st_size, (folder / "slide-01.png").stat().st_size)
            self.assertIsNone(small)

    def test_unreadable_slide_is_skipped_not_fatal(self):
        cls = self._runtime_class()
        with tempfile.TemporaryDirectory() as raw:
            bad = Path(raw) / "slide-01.png"
            bad.write_bytes(b"not an image")
            self.assertIsNone(cls.make_medium_slide(bad, 1))

    def test_reader_prefers_medium_and_swaps_to_original_in_fullscreen(self):
        src = (ROOT / "static/system-learner.js").read_text(encoding="utf8")
        self.assertIn("slideMedium", src)
        self.assertIn("useFullSlideImages", src)


if __name__ == "__main__":
    unittest.main()
