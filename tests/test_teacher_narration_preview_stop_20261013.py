"""老師旁白：試聽到一半按「重錄」或「完成」，試聽聲音必須真的停下來（2026-10-13 回報）。

只移除 <audio> 的 src 屬性不會停止已在播放的聲音；而試聽控制列在 idle 狀態會被隱藏，
老師就找不到地方關掉。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "static" / "teacher-slide-narration-1109.js").read_text(encoding="utf-8")


def function_body(name: str) -> str:
    match = re.search(rf"function {name}\(\)[^{{]*{{", SOURCE)
    assert match, f"{name} not found"
    depth, index = 1, match.end()
    while depth and index < len(SOURCE):
        char = SOURCE[index]
        depth += (char == "{") - (char == "}")
        index += 1
    return SOURCE[match.end():index - 1]


class PreviewAudioStopTests(unittest.TestCase):
    def test_helper_pauses_before_dropping_the_source(self):
        body = function_body("stopPreviewAudio")
        self.assertIn("audio.pause()", body)
        self.assertIn("removeAttribute('src')", body)
        self.assertIn("audio.load()", body)
        self.assertLess(body.index("audio.pause()"), body.index("removeAttribute('src')"))

    def test_discard_and_finish_go_through_clear_recording_which_stops_audio(self):
        self.assertIn("stopPreviewAudio();", function_body("clearRecording"))
        self.assertIn("clearRecording();", function_body("discard"))
        self.assertIn("clearRecording();", function_body("finish"))

    def test_clear_recording_no_longer_only_removes_the_src_attribute(self):
        self.assertNotIn("ui.audio?.removeAttribute('src')", function_body("clearRecording"))

    def test_hiding_the_preview_bar_always_stops_the_sound(self):
        self.assertIn("if (!showAudio) stopPreviewAudio();", function_body("render"))


if __name__ == "__main__":
    unittest.main()
