"""AI question provenance carries a numeric page; candidates start unconfirmed (2026-10-17)."""
import unittest
from pathlib import Path

from teacher_app.assessments import ai_runtime


class AiSourcePageTests(unittest.TestCase):
    def test_page_number_from_hint(self):
        self.assertEqual(ai_runtime.source_page_number("投影片 7"), 7)
        self.assertEqual(ai_runtime.source_page_number("第 12 頁；頁碼已依教材原文自動核對更正"), 12)
        self.assertEqual(ai_runtime.source_page_number("chunk-3"), 0)

    def test_provenance_sets_page_anchor(self):
        chunks = [{"materialId": "m1", "chunkId": "c1", "materialTitle": "凝血", "text": "【投影片 1】凝血因子介紹\n【投影片 2】PT 延長與維生素 K 缺乏有關"}]
        question = {"question": "PT 延長最可能與何者缺乏有關？", "options": ["維生素 K", "鐵", "B12", "葉酸"], "correct": 0, "sourceHint": "投影片 2"}
        out = ai_runtime.attach_question_provenance([question], chunks)[0]
        source = out["answerConfig"]["reviewSource"]
        self.assertEqual((source["anchorType"], source["page"]), ("page", 2))

    def test_candidates_need_teacher_tick(self):
        src = Path("static/admin-ai-questions.js").read_text(encoding="utf-8")
        self.assertIn('id="aid-${id}-${i}-check" type="checkbox" class', src)
        self.assertIn("待老師確認", src)


if __name__ == "__main__":
    unittest.main()
