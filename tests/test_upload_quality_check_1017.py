"""Post-upload quality notes for teachers (2026-10-17)."""
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from teacher_app.materials import quality_check


class QualityCheckTests(unittest.TestCase):
    def test_blank_page_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for n in (1, 2, 3):
                image = Image.new("RGB", (400, 300), "white")
                if n != 2:
                    ImageDraw.Draw(image).text((20, 20), "Slide content " * 4, fill="black")
                    ImageDraw.Draw(image).rectangle((40, 80, 360, 260), outline="black", width=4)
                image.save(d / f"slide-{n}.png")
            Image.new("RGB", (100, 100), "white").save(d / "slide-1-1280.webp")
            self.assertEqual(quality_check.blank_pages(quality_check.page_images(d)), [2])

    def test_findings(self):
        codes = lambda r: [i["code"] for i in r["issues"]]
        self.assertEqual(codes(quality_check.build(page_count=5, blank=[2, 4])), ["blank_pages"])
        self.assertEqual(codes(quality_check.build(media_kind="video", has_audio=False, duration=60)), ["no_audio_track"])
        self.assertEqual(codes(quality_check.build(media_kind="audio", max_db=-80, duration=60)), ["silent_audio"])
        self.assertEqual(codes(quality_check.build(media_kind="video", has_audio=True, max_db=-3, duration=1.5)), ["very_short"])
        self.assertEqual(codes(quality_check.build(page_count=0)), ["no_pages"])
        self.assertEqual(codes(quality_check.build(page_count=10)), [])

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
    def test_silent_wav_measures_as_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "s.wav"
            import subprocess
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "2", str(wav)], capture_output=True, check=True)
            self.assertLessEqual(quality_check.max_volume_db("ffmpeg", wav), quality_check.SILENT_MAX_DB)


if __name__ == "__main__":
    unittest.main()
