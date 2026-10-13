"""faster-whisper 會呼叫 av.open(..., metadata_errors=...)；舊版 PyAV 會報
"open() got an unexpected keyword argument 'metadata_errors'"（2026-10-13 字幕轉錄回報）。
"""
import re
import unittest
from pathlib import Path

TEXT = (Path(__file__).resolve().parents[1] / "requirements-ai-worker.txt").read_text(encoding="utf-8")


class AiWorkerPyAvPinTests(unittest.TestCase):
    def test_pyav_is_pinned_new_enough_next_to_faster_whisper(self):
        self.assertRegex(TEXT, r"(?m)^faster-whisper>=")
        match = re.search(r"(?m)^av>=(\d+),<(\d+)\s*$", TEXT)
        self.assertIsNotNone(match, "requirements-ai-worker.txt must pin av")
        self.assertGreaterEqual(int(match.group(1)), 12)


if __name__ == "__main__":
    unittest.main()
