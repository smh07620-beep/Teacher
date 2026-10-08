import unittest
from unittest.mock import patch

from teacher_app.materials import media_script_jobs as jobs
from teacher_app.materials import media_script_runtime as rt

OUTLINE = [{"title": "採檢", "bullets": ["EDTA 抗凝劑"]}, {"title": "抹片", "bullets": ["推片角度"]}, {"title": "染色", "bullets": []}]
ARGS = dict(source_title="血液抹片", context="ctx", focus="", tone="clinical", target_minutes=5)


class OutlineAwarePromptTests(unittest.TestCase):
    def test_outline_makes_one_paragraph_per_slide(self):
        prompt = rt._prompt(**ARGS, output_type="script", slide_outline=OUTLINE)
        self.assertIn("已核准的投影片大綱（共 3 張）", prompt)
        self.assertIn("1. 採檢：EDTA 抗凝劑", prompt)
        self.assertIn("剛好輸出 3 段", prompt)
        self.assertIn("每段約 466 字", prompt)  # 5 分鐘 × 280 字 = 1400 字 ÷ 3 張

    def test_no_outline_or_other_output_type_keeps_old_prompt(self):
        self.assertNotIn("已核准的投影片大綱", rt._prompt(**ARGS, output_type="script"))
        self.assertNotIn("已核准的投影片大綱", rt._prompt(**ARGS, output_type="handout", slide_outline=OUTLINE))
        self.assertIn("空行把講稿分成多個段落", rt._prompt(**ARGS, output_type="script"))


class LengthCheckTests(unittest.TestCase):
    TARGET_MIN = 5  # 目標 1400 字，超過 1750 字才重試

    def _long(self, chars=2400):
        return "字" * chars

    def test_speakable_chars_ignores_spaces_and_review_note(self):
        self.assertEqual(rt.speakable_chars("甲 乙\n丙\n※ 本講稿需由授課教師確認後方可用於正式教學影音。"), 3)

    def test_too_long_cloud_draft_is_retried_once_and_shorter_wins(self):
        calls = []

        def fake(settings, provider, prompt, progress_callback=None):
            calls.append(prompt)
            return "字" * 1500, {"provider": "groq", "model": "m", "fallbackUsed": False}

        with patch.object(rt, "_generate_body_with_fallback", side_effect=fake):
            body, meta, retried = rt._shorten_if_too_long(None, "PROMPT", self._long(), {"provider": "groq", "model": "m"}, target_minutes=self.TARGET_MIN)
        self.assertTrue(retried)
        self.assertEqual(len(calls), 1)
        self.assertIn("上一版太長", calls[0])
        self.assertEqual(len(body), 1500)

    def test_local_model_is_never_retried(self):
        with patch.object(rt, "_generate_body_with_fallback") as gen:
            body, _meta, retried = rt._shorten_if_too_long(None, "P", self._long(), {"provider": "ollama"}, target_minutes=self.TARGET_MIN)
        gen.assert_not_called()
        self.assertFalse(retried)
        self.assertEqual(len(body), 2400)

    def test_short_or_on_target_drafts_are_left_alone(self):
        with patch.object(rt, "_generate_body_with_fallback") as gen:
            for chars in (200, 1400, 1700):
                _b, _m, retried = rt._shorten_if_too_long(None, "P", "字" * chars, {"provider": "groq"}, target_minutes=self.TARGET_MIN)
                self.assertFalse(retried)
        gen.assert_not_called()

    def test_failed_or_worse_retry_keeps_first_draft(self):
        first = self._long(2000)
        with patch.object(rt, "_generate_body_with_fallback", side_effect=RuntimeError("quota")):
            body, _m, retried = rt._shorten_if_too_long(None, "P", first, {"provider": "groq"}, target_minutes=self.TARGET_MIN)
        self.assertEqual(body, first)
        self.assertTrue(retried)
        with patch.object(rt, "_generate_body_with_fallback", return_value=("字" * 3000, {"provider": "groq", "model": "m"})):
            body, _m, _r = rt._shorten_if_too_long(None, "P", first, {"provider": "groq"}, target_minutes=self.TARGET_MIN)
        self.assertEqual(body, first)


class ApprovedOutlineLookupTests(unittest.TestCase):
    def test_uses_newest_approved_slides_draft_only(self):
        drafts = [
            {"draftType": "slides", "status": "draft", "body": "第 1 張：未核准"},
            {"draftType": "script", "status": "approved", "body": "講稿"},
            {"draftType": "slides", "status": "approved", "body": "第 1 張：採檢\n- EDTA\n第 2 張：抹片\n- 推片"},
        ]
        with patch.object(jobs.media_script_repository, "list_drafts", return_value=drafts):
            outline = jobs._approved_slide_outline("m1")
        self.assertEqual([item["title"] for item in outline], ["採檢", "抹片"])

    def test_returns_none_without_approved_outline_or_on_error(self):
        with patch.object(jobs.media_script_repository, "list_drafts", return_value=[{"draftType": "slides", "status": "draft", "body": "x"}]):
            self.assertIsNone(jobs._approved_slide_outline("m1"))
        with patch.object(jobs.media_script_repository, "list_drafts", side_effect=RuntimeError("db")):
            self.assertIsNone(jobs._approved_slide_outline("m1"))


if __name__ == "__main__":
    unittest.main()
