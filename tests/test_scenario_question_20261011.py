"""Scenario (情境題) question type: validation, grading, secrecy, wiring."""
import json
import re
import unittest
from pathlib import Path

from teacher_app.assessments import runtime_questions, scenario
from teacher_app.exams import grading
from teacher_app.frontend.assets import ASSET_MANIFEST

STATIC = Path(__file__).resolve().parents[1] / "static"


def step(prompt="下一步？", options=("重新採檢", "直接發報告", "停機"), correct=0):
    return {"prompt": prompt, "options": list(options), "correctIndex": correct}


def config(*steps):
    return {"steps": list(steps) or [step(), step("再下一步？", ("通知主管", "忽略"), 1)]}


class ConfigValidationTests(unittest.TestCase):
    def test_valid_config_is_canonicalised(self):
        out = scenario.prepare_config({"steps": [step(" Q1 ", (" a ", "b"), 1), step("Q2", ("x", "y", "z"), 2)]})
        self.assertEqual(out["steps"][0], {"prompt": "Q1", "options": ["a", "b"], "correctIndex": 1})

    def test_rejects_bad_configs_with_readable_messages(self):
        bad = [
            None, {}, {"steps": "x"}, {"steps": [step()]},
            {"steps": [step()] * (scenario.MAX_STEPS + 1)},
            {"steps": [step(), "oops"]},
            {"steps": [step(), step(prompt="")]},
            {"steps": [step(), step(options=("only",))]},
            {"steps": [step(), step(options=("a", "", "c"))]},
            {"steps": [step(), step(correct=5)]},
            {"steps": [step(), step(correct=-1)]},
            {"steps": [step(), {"prompt": "q", "options": ["a", "b"]}]},
        ]
        for value in bad:
            with self.subTest(value=str(value)[:60]):
                with self.assertRaises(ValueError) as ctx:
                    scenario.prepare_config(value)
                self.assertTrue(str(ctx.exception))


class GradingTests(unittest.TestCase):
    def setUp(self):
        self.q = {"question": "病人檢體溶血…", "questionType": "scenario", "answerConfig": config()}

    def test_all_steps_must_be_right(self):
        self.assertTrue(grading.score_question(self.q, [0, 1]))
        self.assertFalse(grading.score_question(self.q, [0, 0]))
        self.assertFalse(grading.score_question(self.q, [1, 1]))

    def test_garbage_and_partial_answers_are_wrong(self):
        for answer in (None, "", [], [0], [0, None], [0, 1, 1], "01", {"0": 0}, [True, True], [0, "x"], 0):
            with self.subTest(answer=answer):
                self.assertFalse(grading.score_question(self.q, answer))

    def test_grade_attempt_records_choices(self):
        out = grading.grade_attempt([self.q], [[0, 1]], 60)
        self.assertEqual(out["score"], 100)
        self.assertEqual(out["answersDetail"][0]["userAnswer"], "1.A　2.B")
        wrong = grading.grade_attempt([self.q], [[0, None]], 60)
        self.assertEqual(wrong["score"], 0)
        self.assertEqual(wrong["answersDetail"][0]["userAnswer"], "1.A　2.未答")

    def test_learner_payload_keeps_text_but_never_the_right_answer(self):
        for safe in (grading.sanitize_question(self.q), grading.review_question(self.q)):
            self.assertNotIn("correctIndex", json.dumps(safe, ensure_ascii=False))
            steps = safe["answerConfig"]["steps"]
            self.assertEqual(steps[0]["options"], ["重新採檢", "直接發報告", "停機"])
            self.assertEqual(steps[0]["prompt"], "下一步？")
        # the stored question is untouched
        self.assertEqual(self.q["answerConfig"]["steps"][0]["correctIndex"], 0)


class NormalisationTests(unittest.TestCase):
    def normalise(self, data, existing=None):
        return runtime_questions._normalized_common(data, existing=existing)

    def test_create(self):
        out = self.normalise({"question": "case", "questionType": "scenario", "options": ["a", "b"], "answerConfig": config()})
        self.assertEqual(out["questionType"], "scenario")
        self.assertEqual(out["options"], [])
        self.assertEqual(len(out["answerConfig"]["steps"]), 2)

    def test_create_without_steps_is_rejected(self):
        with self.assertRaises(ValueError):
            self.normalise({"question": "case", "questionType": "scenario", "answerConfig": {}})

    def test_inline_editor_without_steps_keeps_saved_case(self):
        existing = {"question": "old", "questionType": "scenario", "answerConfig": config()}
        out = self.normalise({"question": "new text", "questionType": "scenario", "answerConfig": {}, "options": []}, existing=existing)
        self.assertEqual(out["question"], "new text")
        self.assertEqual(out["answerConfig"]["steps"], existing["answerConfig"]["steps"])

    def test_plain_edit_keeps_saved_case(self):
        existing = {"question": "old", "questionType": "scenario", "answerConfig": config()}
        out = self.normalise({"active": False}, existing=existing)
        self.assertEqual(out["answerConfig"]["steps"], existing["answerConfig"]["steps"])
        self.assertFalse(out["active"])

    def test_new_steps_are_revalidated(self):
        existing = {"question": "old", "questionType": "scenario", "answerConfig": config()}
        with self.assertRaises(ValueError):
            self.normalise({"answerConfig": {"steps": [step()]}}, existing=existing)

    def test_switching_type_drops_steps(self):
        existing = {"question": "q", "questionType": "scenario", "answerConfig": config()}
        out = self.normalise({"questionType": "choice", "options": ["a", "b"], "answerConfig": config()}, existing=existing)
        self.assertNotIn("steps", out["answerConfig"])

    def test_bulk_import_cannot_create_scenario(self):
        self.assertNotIn("scenario", runtime_questions.IMPORTABLE_TYPES)
        self.assertIn("scenario", runtime_questions.QUESTION_TYPES)


class WiringTests(unittest.TestCase):
    def read(self, name):
        return (STATIC / name).read_text(encoding="utf-8")

    def test_scripts_are_injected_once(self):
        body = ASSET_MANIFEST["system"]["body"]
        for name in ("learner-scenario-question-1011.js", "admin-scenario-question-1011.js"):
            self.assertEqual(body.count("/" + name), 1)

    def test_no_inline_handlers_eval_or_innerhtml_on_teacher_side(self):
        for name in ("learner-scenario-question-1011.js", "admin-scenario-question-1011.js"):
            src = self.read(name)
            self.assertIsNone(re.search(r"\son[a-z][a-z0-9_-]*\s*=", src, re.IGNORECASE))
            self.assertNotIn("eval(", src)
        self.assertNotIn("innerHTML", self.read("admin-scenario-question-1011.js"))

    def test_csp_action_allowed_and_defined(self):
        self.assertIn("'scenarioPick'", self.read("system-csp-actions.js"))
        self.assertIn("root.scenarioPick =", self.read("learner-scenario-question-1011.js"))

    def test_learner_script_never_references_the_answer_key(self):
        self.assertNotIn("correctIndex", self.read("learner-scenario-question-1011.js"))

    def test_canonical_owners_call_the_modules(self):
        self.assertIn("ScenarioQuestion.render(", self.read("system-exam.js"))
        self.assertIn("function setScenarioAnswer(", self.read("system-exam.js"))
        self.assertIn("AdminScenarioQuestion?.syncForm(", self.read("admin-question-panel.js"))
        self.assertIn("AdminScenarioQuestion?.collect(", self.read("admin-question-actions.js"))
        self.assertIn('value="scenario"', self.read("admin-question-bank.js"))


if __name__ == "__main__":
    unittest.main()
