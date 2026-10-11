import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FiveQuestionCapTests(unittest.TestCase):
    def test_picker_offers_only_three_or_five(self):
        src = (ROOT / "static" / "admin-question-bank.js").read_text(encoding="utf-8")
        i = src.index('id="ai-count-${c.id}"')
        block = src[i:i + 400]
        self.assertIn('value="3"', block)
        self.assertIn('value="5" selected', block)
        self.assertNotIn('value="10"', block)
        self.assertNotIn('value="15"', block)

    def test_server_default_cap_is_five_in_blueprint(self):
        text = (ROOT / "render.yaml").read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertIn('- key: AI_MAX_QUESTIONS\n        value: "5"', text)


if __name__ == "__main__":
    unittest.main()
