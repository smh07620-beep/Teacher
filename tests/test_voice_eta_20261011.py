"""AI 語音倒數時間：快取段落不計入、學到的速度重開機後還在 (2026-10-11)。"""
import io
import os
import tempfile
import unittest
import wave
from unittest.mock import patch

from teacher_app.materials import media_audio_runtime as runtime


def _wav(seconds=1):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * 24000 * seconds)
    return buffer.getvalue()


class VoiceEtaTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = patch.dict(os.environ, {"KOKORO_CACHE_DIR": tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self._saved = dict(runtime._LEARNED_RATE)
        runtime._LEARNED_RATE.clear()
        self.addCleanup(lambda: (runtime._LEARNED_RATE.clear(), runtime._LEARNED_RATE.update(self._saved)))

    def test_learned_speed_survives_a_worker_restart(self):
        runtime._remember_rate(0.1)
        runtime._LEARNED_RATE.clear()  # simulates a fresh process
        self.assertAlmostEqual(runtime._seconds_per_char(), 0.1)

    def test_cached_segments_are_detected(self):
        path = runtime._tts_cache_file("已經合成過", "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 2048)
        self.assertTrue(runtime._is_tts_cached("已經合成過", ""))
        self.assertFalse(runtime._is_tts_cached("還沒合成", ""))

    def test_countdown_excludes_cached_segments(self):
        runtime._remember_rate(1.0)  # 1 second per character, easy arithmetic
        cached_text, new_text = "甲" * 10, "乙" * 20
        path = runtime._tts_cache_file(cached_text, "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 2048)
        details = []
        with patch.object(runtime, "_synthesize", return_value=(_wav(), "m")), \
             patch.object(runtime.tts_text, "apply_pronunciation", lambda text: text):
            runtime._synthesize_segmented(
                [cached_text, new_text], voice="", instructions="",
                progress_callback=lambda percent, stage, detail: details.append(detail),
            )
        self.assertIn("預估還需約 20 秒", details[0])  # not 30: the cached 10 characters cost nothing


if __name__ == "__main__":
    unittest.main()
