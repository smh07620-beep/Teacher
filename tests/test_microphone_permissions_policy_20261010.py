"""Teacher narration recording needs the microphone on our own origin only."""
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "teacher_app" / "common" / "security.py"


class MicrophonePolicyTest(unittest.TestCase):
    def test_microphone_allowed_for_self_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("microphone=(self)", text)
        self.assertIn("camera=()", text)
        self.assertIn("geolocation=()", text)


if __name__ == "__main__":
    unittest.main()
