import re
import unittest
from pathlib import Path

from teacher_app.materials import media_audio_runtime as rt

JS = Path(__file__).resolve().parents[1] / "static" / "teacher-media-audio-1014.js"


class VoiceEtaTest(unittest.TestCase):
    def test_format_eta(self):
        self.assertEqual(rt.format_eta(0), "預估還需約 1 秒")
        self.assertEqual(rt.format_eta(42), "預估還需約 42 秒")
        self.assertEqual(rt.format_eta(125), "預估還需約 2 分 05 秒")

    def test_segment_progress_contains_eta(self):
        messages = []
        rt._LEARNED_RATE.clear()
        texts = ["甲" * 20, "乙" * 40]
        rt.build_segmented_wav  # keep import used
        original = rt._synthesize
        import io, wave
        def fake(text, *, voice, instructions):
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\0\0" * 2400)
            return buf.getvalue(), "m"
        rt._synthesize = fake
        try:
            rt._synthesize_segmented(texts, voice="zf_001", instructions="", progress_callback=lambda p, s, d: messages.append(d))
        finally:
            rt._synthesize = original
        self.assertEqual(len(messages), 2)
        self.assertTrue(all("預估還需約" in m for m in messages))
        self.assertIn("預估還需約 15 秒", messages[0])  # 60 chars * 0.25 s

    def test_frontend_counts_down(self):
        text = JS.read_text(encoding="utf-8")
        self.assertIn("預估還需約", text)
        self.assertIn("setInterval", text)
        self.assertIn("stopEtaTimer", text)


if __name__ == "__main__":
    unittest.main()
