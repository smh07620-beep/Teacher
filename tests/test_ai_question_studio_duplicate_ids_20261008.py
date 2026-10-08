"""The AI question studio must work even when the same exam panel exists twice in the DOM."""
import re
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1].joinpath("static", "admin-ai-questions.js").read_text(encoding="utf-8")


class DuplicateIdTests(unittest.TestCase):
    def test_studio_picks_the_visible_copy(self):
        self.assertIn("const pickEl = (name, id) =>", SRC)
        self.assertIn("getClientRects().length", SRC)

    def test_no_direct_lookup_for_studio_elements(self):
        self.assertEqual([], re.findall(r"document\.getElementById\(`ai-[a-z-]+-\$\{id\}`\)", SRC))


if __name__ == "__main__":
    unittest.main()


class AutoSelectTests(unittest.TestCase):
    def test_generated_audio_is_not_auto_selected_for_question_generation(self):
        self.assertIn("!['video','audio'].includes(kind(m)[0])", SRC)
        self.assertNotIn("filter(m=>kind(m)[0]!=='video').slice(0,4)", SRC)
