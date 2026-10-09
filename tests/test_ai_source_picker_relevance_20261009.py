import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AiSourcePickerRelevanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = ROOT.joinpath("static", "admin-ai-questions.js").read_text(encoding="utf-8")
        cls.bank = ROOT.joinpath("static", "admin-question-bank.js").read_text(encoding="utf-8")

    def test_default_is_own_course_materials(self):
        for token in ("ownMaterial", "m.category===id", "s.courseId=box.dataset.courseId"):
            self.assertIn(token, self.js)

    def test_related_suggestions_are_limited(self):
        for token in ("relatedMap", "suggestedIds", "n>=4", "slice(0,3)", "可能相關（其他課程）"):
            self.assertIn(token, self.js)

    def test_other_courses_hidden_behind_button(self):
        self.assertIn("顯示其他課程的教材", self.js)
        self.assertIn("showOthers", self.js)

    def test_question_bank_passes_course_context(self):
        self.assertIn("data-course-id", self.bank)
        self.assertIn("data-title", self.bank)


if __name__ == "__main__":
    unittest.main()
