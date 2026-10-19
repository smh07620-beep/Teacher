"""Per-attempt option shuffle maps answers back to the teacher's order (2026-10-17)."""
import random
import unittest

from teacher_app.exams import grading, option_order


def q(**kw):
    base = {"id": "q1", "questionType": "choice", "question": "?", "options": ["甲", "乙", "丙", "丁"], "correct": 2}
    base.update(kw)
    return base


class OptionShuffleTests(unittest.TestCase):
    def test_shown_answer_grades_against_original(self):
        question = option_order.assign([q()], rng=random.Random(3))[0]
        shown = option_order.present(question)
        self.assertNotIn("optionOrder", shown)
        self.assertEqual(sorted(shown["options"]), sorted(question["options"]))
        shown_index = shown["options"].index("丙")
        original = option_order.to_original(question, shown_index)
        self.assertEqual(original, 2)
        self.assertTrue(grading.score_question(question, original))

    def test_multi_maps_every_index(self):
        question = option_order.assign([q(questionType="multi", answerConfig={"correctIndices": [0, 3]})], rng=random.Random(5))[0]
        shown = option_order.present(question)
        picks = [shown["options"].index("甲"), shown["options"].index("丁")]
        self.assertEqual(option_order.to_original(question, picks), [0, 3])

    def test_positional_options_and_true_false_stay_fixed(self):
        fixed = option_order.assign([q(options=["A", "B", "以上皆是"]), q(questionType="true_false", options=["對", "錯"])])
        self.assertTrue(all("optionOrder" not in item for item in fixed))

    def test_teacher_can_switch_off(self):
        self.assertNotIn("optionOrder", option_order.assign([q()], enabled=False)[0])

    def test_unanswered_stays_unanswered(self):
        question = option_order.assign([q()], rng=random.Random(1))[0]
        self.assertIsNone(option_order.to_original(question, None))


if __name__ == "__main__":
    unittest.main()
