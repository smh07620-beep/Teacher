import ast
import unittest
from pathlib import Path


def load_namespace():
    source = Path(__file__).parents[1].joinpath("exam_integrity.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    selected = []
    wanted = {"_sanitize_answer_config", "sanitize_question", "_normalize_indices", "score_question"}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted:
            selected.append(node)
    namespace = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "exam_integrity.py", "exec"), namespace)
    return namespace


NS = load_namespace()


class ExamIntegrityTests(unittest.TestCase):
    def test_learner_question_removes_answer_keys(self):
        q = {
            "question": "Q",
            "correct": 2,
            "explanation": "Because C",
            "answerConfig": {"correctIndices": [1, 2], "acceptedAnswers": ["secret"], "mediaUrl": "/x.mp4", "pauseAt": 12},
        }
        safe = NS["sanitize_question"](q)
        self.assertNotIn("correct", safe)
        self.assertNotIn("explanation", safe)
        self.assertNotIn("correctIndices", safe["answerConfig"])
        self.assertNotIn("acceptedAnswers", safe["answerConfig"])
        self.assertEqual(safe["answerConfig"]["mediaUrl"], "/x.mp4")

    def test_server_scores_single_choice(self):
        q = {"questionType": "choice", "correct": 1, "answerConfig": {}}
        self.assertTrue(NS["score_question"](q, 1))
        self.assertFalse(NS["score_question"](q, 0))

    def test_server_scores_multi_as_exact_set(self):
        q = {"questionType": "multi", "answerConfig": {"correctIndices": [0, 2]}}
        self.assertTrue(NS["score_question"](q, [2, 0]))
        self.assertFalse(NS["score_question"](q, [0]))

    def test_fill_respects_case_sensitivity(self):
        q = {"questionType": "fill", "answerConfig": {"acceptedAnswers": ["HbA1c"], "caseSensitive": False}}
        self.assertTrue(NS["score_question"](q, "hba1c"))
        q["answerConfig"]["caseSensitive"] = True
        self.assertFalse(NS["score_question"](q, "hba1c"))

    def test_essay_is_not_auto_graded(self):
        self.assertIsNone(NS["score_question"]({"questionType": "essay", "answerConfig": {}}, "text"))


if __name__ == "__main__":
    unittest.main()
