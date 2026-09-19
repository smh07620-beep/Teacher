import unittest

from ai_privacy import deidentify_text
from teacher_app.assessments import ai_runtime


class AiPrivacyTests(unittest.TestCase):
    def test_masks_common_identifiers(self):
        text = "姓名：王小明 病歷號: A1234567 手機 0912345678 DOB: 1980-01-02"
        masked, count = deidentify_text(text)
        self.assertGreaterEqual(count, 3)
        self.assertNotIn("王小明", masked)
        self.assertNotIn("A1234567", masked)
        self.assertNotIn("0912345678", masked)

    def test_non_sensitive_text_is_preserved(self):
        text = "血糖檢驗前應確認檢體與分析品質。"
        masked, count = deidentify_text(text)
        self.assertEqual(masked, text)
        self.assertEqual(count, 0)

    def test_privacy_targets_are_explicit_public_ai_runtime_functions(self):
        self.assertEqual(
            ai_runtime.EXTERNAL_AI_TEXT_EXTRACTOR_TARGETS,
            ("extract_material_text_for_ai", "groq_transcribe"),
        )
        for name in ai_runtime.EXTERNAL_AI_TEXT_EXTRACTOR_TARGETS:
            self.assertTrue(callable(getattr(ai_runtime, name, None)), name)


if __name__ == "__main__":
    unittest.main()
