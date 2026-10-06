import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AiVideoBrowserE2EContractTests(unittest.TestCase):
    def test_linux_ci_uses_branded_chrome_and_keeps_native_playback_mandatory(self):
        source = (ROOT / "tests" / "playwright" / "ai-video-fullstack.spec.js").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "product-golden-path-checks.yml").read_text(encoding="utf-8")

        self.assertIn("channel:'chrome'", source)
        self.assertIn("Range:'bytes=0-1023'", source)
        self.assertIn("CI browser must advertise H.264/AAC MP4 support", source)
        self.assertIn("Browser must load MP4 metadata and expose a positive duration", source)
        self.assertIn("Browser must advance real MP4 playback", source)
        self.assertNotIn("if(mediaState.ready)", source)
        self.assertIn("npx playwright install chrome", workflow)


if __name__ == "__main__":
    unittest.main()
