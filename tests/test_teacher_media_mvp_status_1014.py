from pathlib import Path
import unittest

from pgy_frontend import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class TeacherMediaMvpStatus1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "teacher-media-mvp-status-1014.js").read_text(encoding="utf-8")
        cls.body = ASSET_MANIFEST["system"]["body"]

    def test_asset_is_loaded_after_media_audio(self):
        self.assertIn("/teacher-media-mvp-status-1014.js", self.body)
        self.assertLess(
            self.body.index("/teacher-media-audio-1014.js"),
            self.body.index("/teacher-media-mvp-status-1014.js"),
        )

    def test_shipped_media_capabilities_keep_compact_readiness_without_duplicate_banner(self):
        for marker in (
            "可使用｜AI 草稿＋教師核准",
            "可使用｜真人錄音＋AI 語音",
            "可使用｜攝影機＋螢幕錄影",
        ):
            self.assertIn(marker, self.source)
        self.assertIn("teacher-media-mvp-summary-1014", self.source)
        self.assertIn("?.remove()", self.source)
        self.assertNotIn("10/14 MVP READY", self.source)
        self.assertNotIn("✓ 回流教材", self.source)
        self.assertNotIn("下一實作切點", self.source)

    def test_presentation_does_not_redefine_server_authorization(self):
        self.assertIn("has('material.manage')", self.source)
        for forbidden in ("X-Admin-Key", "getAdminKey", "fetch('/api/users", "localStorage.setItem('role"):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
