import unittest

from ai_privacy import deidentify_text


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


if __name__ == "__main__":
    unittest.main()
