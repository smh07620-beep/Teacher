"""AI question quality: top-up when short, shortfall explanation, answer spread, page citations."""
import io
import random
import unittest
import zipfile
from collections import Counter
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from teacher_app.assessments import ai_jobs, ai_runtime, answer_balance, free_ai_fallback
from teacher_app.materials import classification


def _choice(stem, options, correct, **extra):
    return {"questionType": "choice", "question": stem, "options": list(options), "correct": correct,
            "answerConfig": {}, **extra}


_TOPICS = ["新批號校正液下載", "平行測試允收", "外部能力試驗收件", "維修後放行", "CV 月審查", "QC Chart 圓點",
           "失控判讀順序", "儀器相關性頻率", "試劑第一階段驗收", "效期檢查", "電極保養", "條碼列印時機",
           "校正失敗處理", "品管品回溫", "結果傳送期限", "異常通報流程", "年度評估內容", "盤點作業"]


def _raw_choice(index):
    return {"questionType": "choice", "question": f"關於{_TOPICS[index % len(_TOPICS)]}，下列哪一項敘述符合院內規定？",
            "options": ["甲", "乙", "丙", "丁"], "correct": 1}


class AnswerBalanceTests(unittest.TestCase):
    def test_correct_answers_spread_evenly_and_stay_correct(self):
        questions = [
            _choice(f"題幹{i}", [f"對{i}", f"錯{i}a", f"錯{i}b", f"錯{i}c"], 0)
            for i in range(8)
        ]
        # 模型最愛把答案放 B
        for q in questions:
            q["options"][0], q["options"][1] = q["options"][1], q["options"][0]
            q["correct"] = 1
        moved = answer_balance.balance_answer_positions(questions, random.Random(7))
        self.assertEqual(moved, 8)
        self.assertEqual(sorted(Counter(q["correct"] for q in questions).values()), [2, 2, 2, 2])
        for i, q in enumerate(questions):
            self.assertEqual(q["options"][q["correct"]], f"對{i}")
            self.assertEqual(sorted(q["options"]), sorted([f"對{i}", f"錯{i}a", f"錯{i}b", f"錯{i}c"]))

    def test_multi_answer_indices_follow_their_options(self):
        question = {"questionType": "multi", "question": "下列哪些屬於 QC 失控規則", "correct": 0,
                    "options": ["13S", "22S", "平均值", "單位"],
                    "answerConfig": {"correctIndices": [0, 1]}}
        for seed in range(10):
            copy = {**question, "options": list(question["options"]),
                    "answerConfig": {"correctIndices": [0, 1]}}
            answer_balance.balance_answer_positions([copy], random.Random(seed))
            chosen = {copy["options"][i] for i in copy["answerConfig"]["correctIndices"]}
            self.assertEqual(chosen, {"13S", "22S"})
            self.assertEqual(copy["correct"], min(copy["answerConfig"]["correctIndices"]))

    def test_order_dependent_numeric_and_other_types_are_left_alone(self):
        keep_all = _choice("哪一項正確", ["血糖", "尿素", "肌酸酐", "以上皆是"], 3)
        keep_ref = _choice("請問 B 和 C 何者正確", ["甲", "乙", "丙", "丁"], 1)
        keep_letter = _choice("下列何者正確", ["甲", "乙", "丙", "丁"], 2, explanation="因此選項 C 為正確答案")
        keep_numeric = _choice("允收差異上限為何", ["1%", "2%", "5%", "10%"], 2)
        true_false = {"questionType": "true_false", "question": "對嗎", "options": ["是", "否"], "correct": 1}
        essay = {"questionType": "essay", "question": "請說明", "options": [], "correct": 0}
        originals = [dict(q, options=list(q["options"])) for q in
                     (keep_all, keep_ref, keep_letter, keep_numeric, true_false, essay)]
        batch = [keep_all, keep_ref, keep_letter, keep_numeric, true_false, essay]
        self.assertEqual(answer_balance.balance_answer_positions(batch, random.Random(1)), 0)
        self.assertEqual(batch, originals)

    def test_non_numeric_labels_that_merely_contain_numbers_are_still_moved(self):
        # 截圖中的題目：選項是 1/2 TEa、1/3 TEa、±1SD、±3SD，沒有天然的數值順序
        q = _choice("TEa > 10% 時差異範圍", ["差異 ≤ 1/2 TEa", "差異 ≤ 1/3 TEa", "差異 ≤ ±1SD", "差異 ≤ ±3SD"], 1)
        positions = set()
        for seed in range(20):
            copy = dict(q, options=list(q["options"]), correct=1)
            answer_balance.balance_answer_positions([copy], random.Random(seed))
            self.assertEqual(copy["options"][copy["correct"]], "差異 ≤ 1/3 TEa")
            positions.add(copy["correct"])
        self.assertGreater(len(positions), 1)


class NormalizeTests(unittest.TestCase):
    def test_malformed_items_are_reported_and_do_not_crowd_out_valid_ones(self):
        parsed = {"questions": [
            {"questionType": "choice", "question": "選項不足", "options": ["a", "b"], "correct": 0},
            {"questionType": "fill", "question": "沒有答案", "options": []},
            {"questionType": "choice", "question": "", "options": ["a", "b", "c", "d"]},
            _raw_choice(1), _raw_choice(2), _raw_choice(3),
        ]}
        result = ai_runtime.normalize_ai_questions(parsed, 3)
        self.assertEqual([q["question"] for q in result], [_raw_choice(i)["question"] for i in (1, 2, 3)])
        self.assertEqual(len(result.dropped), 3)
        self.assertIn("選項不是 4 個", result.dropped[0])

    def test_extra_questions_beyond_requested_count_are_trimmed(self):
        result = ai_runtime.normalize_ai_questions({"questions": [_raw_choice(i) for i in range(6)]}, 4)
        self.assertEqual(len(result), 4)
        self.assertEqual(result.dropped, [])

    def test_duplicate_stems_are_detected(self):
        a = "新批號平行測試時，TEa > 10% 的允收標準為何？"
        b = "新批號平行測試時 TEa > 10% 的允收標準為何"
        self.assertTrue(ai_runtime.is_duplicate_stem(b, [a]))
        self.assertFalse(ai_runtime.is_duplicate_stem("維修保養後第一步要做什麼", [a]))
        # 只差一個比較符號的兩題是不同的題目，不能當成重複
        self.assertFalse(ai_runtime.is_duplicate_stem("新批號平行測試時，TEa ≤ 10% 的允收標準為何？", [a]))
        merged = ai_runtime.merge_unique_questions([{"question": a}], [{"question": b}, {"question": "完全不同的題目內容說明"}])
        self.assertEqual(len(merged), 2)


class GroqTopUpTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict("os.environ", {"AI_RATE_LIMIT_RETRY_SECONDS": "0"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.settings = ai_runtime.AISettings(
            provider="groq", groq_api_key="g", groq_model="m", groq_transcribe_model="w",
            gemini_api_key="", gemini_model="g", openai_api_key="", openai_model="o",
            source_max_chars=50000, max_questions=15, media_max_mb=300, max_materials=4,
            video_frame_count=3, free_only_mode=True,
        )

    def _run(self, original_generate, count=10):
        runtime = SimpleNamespace(
            generate_ai_questions_from_materials=original_generate,
            active_ai_provider=lambda: "groq", ai_model_name=lambda: "groq-model",
            paths_provider=lambda: None,
        )
        free_ai_fallback.install_question_runtime_fallback(runtime)
        with patch.object(free_ai_fallback.ai_runtime, "ai_settings", return_value=self.settings), \
                patch.object(free_ai_fallback, "provider_chain", return_value=["groq"]), \
                patch.object(free_ai_fallback.time, "sleep") as sleep:
            result = runtime.generate_ai_questions_from_materials(
                [{"filename": "a.pptx"}], category_id="c", count=count, qtype="mixed_all",
                difficulty="standard", focus="", strategy="balanced",
            )
        return result, sleep

    def test_short_batches_are_topped_up_to_the_requested_count(self):
        calls, serial = [], iter(range(1000))

        def generate(entries, **kwargs):
            calls.append(kwargs["count"])
            # 每次只有 3 題通過格式檢查
            good = [_raw_choice(next(serial)) for _ in range(min(3, kwargs["count"]))]
            return ai_runtime.QuestionBatch(good, dropped=["第 4 題選項不是 4 個"]), "標題", ["text"]

        (questions, title, kinds), sleep = self._run(generate)
        self.assertEqual(len(questions), 10)  # 每輪只有 3 題合格：2 個主批次 + 2 輪補題 = 3+3+3+1
        self.assertGreaterEqual(len(calls), 3)
        self.assertEqual(calls[0], 5)
        self.assertIsInstance(questions, ai_runtime.QuestionBatch)
        self.assertTrue(questions.dropped)

    def test_top_up_reaches_the_target_when_the_ai_catches_up(self):
        calls, serial = [], iter(range(1000))

        def generate(entries, **kwargs):
            calls.append(kwargs["count"])
            n = 3 if len(calls) == 1 else kwargs["count"]
            return ai_runtime.QuestionBatch([_raw_choice(next(serial)) for _ in range(n)]), "標題", ["text"]

        (questions, _t, _k), _sleep = self._run(generate, count=5)
        self.assertEqual(len(questions), 5)
        self.assertEqual(calls, [5, 2])

    def test_failed_top_up_keeps_questions_already_generated(self):
        calls, serial = [], iter(range(1000))

        def generate(entries, **kwargs):
            calls.append(kwargs["count"])
            if len(calls) > 1:
                raise RuntimeError("Groq 免費 AI 額度已達上限，請稍後再試。")
            return ai_runtime.QuestionBatch([_raw_choice(next(serial)) for _ in range(3)]), "標題", ["text"]

        (questions, _t, _k), _sleep = self._run(generate, count=5)
        self.assertEqual(len(questions), 3)
        self.assertTrue(any("補題時發生問題" in note for note in questions.notes))

    def test_first_batch_failure_still_propagates_for_provider_fallback(self):
        def generate(entries, **kwargs):
            raise RuntimeError("AI 回傳的題目未通過格式檢查，請重新產生。")

        with self.assertRaises(RuntimeError):
            self._run(generate, count=5)

    def test_repeated_questions_are_not_counted_twice(self):
        def generate(entries, **kwargs):
            return ai_runtime.QuestionBatch([_raw_choice(0), _raw_choice(1)]), "標題", ["text"]

        (questions, _t, _k), _sleep = self._run(generate, count=4)
        self.assertEqual(len(questions), 2)
        self.assertTrue(any("重複" in note for note in questions.notes))


class ShortfallNoteTests(unittest.TestCase):
    def test_no_note_when_complete(self):
        self.assertEqual(ai_jobs.shortfall_note(5, [{}] * 5), "")
        self.assertEqual(ai_jobs.shortfall_note(0, []), "")

    def test_note_explains_dropped_and_notes(self):
        batch = ai_runtime.QuestionBatch(
            [{}] * 6, dropped=["第 2 題選項不是 4 個", "第 5 題填空題沒有可接受答案"], notes=["2 題與已出的題目重複而略過"]
        )
        note = ai_jobs.shortfall_note(10, batch)
        self.assertIn("你要求 10 題，實際取得 6 題", note)
        self.assertIn("2 題格式不完整", note)
        self.assertIn("選項不是 4 個", note)
        self.assertIn("重複", note)

    def test_note_has_a_generic_reason_for_plain_lists(self):
        self.assertIn("只回傳了這些題目", ai_jobs.shortfall_note(10, [{}] * 4))

    def test_generation_result_carries_note_and_balanced_answers(self):
        questions = ai_runtime.QuestionBatch(
            [_choice(f"獨立題目編號{i}說明", ["甲", "乙", "丙", "丁"], 1) for i in range(4)]
        )
        runtime = SimpleNamespace(
            generate_ai_questions_from_materials=lambda materials, **kw: (questions, "標題", ["text"]),
            infer_ai_strategy=lambda m: "balanced", active_ai_provider=lambda: "groq",
            ai_model_name=lambda: "model",
        )
        material = {"id": "m1", "active": True, "filename": "a.pptx"}
        with patch.object(ai_jobs.ai_privacy, "external_enabled", return_value=True), \
                patch.object(ai_jobs.material_repository, "get_material", return_value=material):
            result = ai_jobs.run_generation_sync(
                runtime, {"materialIds": ["m1"], "count": 10, "quizCategoryId": "c", "questionType": "mixed"}
            )
        self.assertEqual((result["requestedCount"], result["returnedCount"]), (10, 4))
        self.assertIn("實際取得 4 題", result["shortfallNote"])
        self.assertEqual(sorted(q["correct"] for q in result["questions"]), [0, 1, 2, 3])


    def test_balancing_is_skipped_only_in_the_isolated_e2e_stub_mode(self):
        questions = [_choice("獨立題目說明一二三", ["甲", "乙", "丙", "丁"], 0) for _ in range(4)]
        runtime = SimpleNamespace(
            generate_ai_questions_from_materials=lambda materials, **kw: (questions, "標題", ["text"]),
            infer_ai_strategy=lambda m: "balanced", active_ai_provider=lambda: "groq",
            ai_model_name=lambda: "model",
        )
        material = {"id": "m1", "active": True, "filename": "a.pptx"}
        env = {"TEACHER_E2E_TEST_MODE": "1", "TEACHER_E2E_DETERMINISTIC_STUBS": "1"}
        with patch.dict("os.environ", env), \
                patch.object(ai_jobs.ai_privacy, "external_enabled", return_value=True), \
                patch.object(ai_jobs.material_repository, "get_material", return_value=material):
            result = ai_jobs.run_generation_sync(
                runtime, {"materialIds": ["m1"], "count": 4, "quizCategoryId": "c", "questionType": "mixed"}
            )
        self.assertEqual([q["correct"] for q in result["questions"]], [0, 0, 0, 0])


class PageCitationTests(unittest.TestCase):
    CHUNKS = [{
        "materialId": "m1", "chunkId": "m1:chunk-0001", "materialTitle": "t", "section": "投影片 12",
        "text": (
            "[投影片 12]\n05｜TEa% ＆ CV%：月／年度品質審查怎麼看\nCV% = SD ÷ Mean × 100%\n\n"
            "[投影片 13]\n06｜QC Chart：cobas pro 將品管結果與統計呈現在 Routine > QC Chart\n"
            "操作步驟\n3\n確認圓點\n綠色＝可接受；紅色＝超出範圍\n\n"
            "[投影片 14]\n06｜QC Chart 檢討：既有生化組採 Multi-Rule 12S 13S 22S R4S\n偏移 趨勢 檢討順序"
        ),
    }]

    def test_off_by_one_slide_number_is_corrected(self):
        question = {
            "questionType": "choice", "question": "QC Chart 中圓點顏色代表什麼",
            "options": ["綠色代表可接受", "紅色代表可接受", "藍色代表可接受", "黑色代表可接受"], "correct": 0,
            "explanation": "根據投影片 14 的操作步驟第 3 點，確認圓點，綠色代表可接受，紅色代表超出範圍。",
            "sourceHint": "投影片 14", "sourceEvidence": "操作步驟第 3 點確認圓點綠色可接受紅色超出範圍",
            "sourceMaterialId": "m1", "chunkId": "m1:chunk-0001",
        }
        [fixed] = ai_runtime.attach_question_provenance([question], self.CHUNKS)
        self.assertIn("投影片 13 的操作步驟第 3 點", fixed["explanation"])
        self.assertTrue(fixed["sourceHint"].startswith("投影片 13"))
        self.assertIn("自動核對更正", fixed["sourceHint"])
        self.assertIn("投影片 13", fixed["answerConfig"]["reviewSource"]["regionHint"])

    def test_correct_citation_is_not_touched(self):
        question = {
            "questionType": "choice", "question": "QC Chart 中圓點顏色代表什麼",
            "options": ["綠色代表可接受", "紅", "藍", "黑"], "correct": 0,
            "explanation": "根據投影片 13 的操作步驟，綠色代表可接受。", "sourceHint": "投影片 13",
            "sourceMaterialId": "m1", "chunkId": "m1:chunk-0001",
        }
        [same] = ai_runtime.attach_question_provenance([question], self.CHUNKS)
        self.assertEqual(same["sourceHint"], "投影片 13")
        self.assertNotIn("自動核對", same["sourceHint"])

    def test_two_different_citations_are_left_alone(self):
        question = {
            "questionType": "choice", "question": "QC Chart 中圓點顏色代表什麼",
            "options": ["綠色代表可接受", "紅", "藍", "黑"], "correct": 0,
            "explanation": "參考投影片 12 與投影片 14。", "sourceHint": "投影片 14",
            "sourceMaterialId": "m1", "chunkId": "m1:chunk-0001",
        }
        [same] = ai_runtime.attach_question_provenance([question], self.CHUNKS)
        self.assertIn("投影片 12 與投影片 14", same["explanation"])

    def test_missing_hint_points_at_best_matching_slide_not_chunk_start(self):
        question = {
            "questionType": "choice", "question": "QC Chart 中圓點顏色代表什麼",
            "options": ["綠色代表可接受", "紅", "藍", "黑"], "correct": 0, "explanation": "",
            "sourceMaterialId": "m1", "chunkId": "m1:chunk-0001",
        }
        [filled] = ai_runtime.attach_question_provenance([question], self.CHUNKS)
        self.assertEqual(filled["sourceHint"], "投影片 13")


class PptxSlideOrderTests(unittest.TestCase):
    @staticmethod
    def _slide(text):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree>'
            f"<p:sp><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp>"
            "</p:spTree></p:cSld></p:sld>"
        )

    def _deck(self, tmp, order):
        path = Path(tmp) / "deck.pptx"
        ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId{i + 1}"/>' for i in range(len(order)))
        rels = "".join(
            f'<Relationship Id="rId{i + 1}" Type="x" Target="slides/slide{n}.xml"/>' for i, n in enumerate(order)
        )
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "ppt/presentation.xml",
                '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f"<p:sldIdLst>{ids}</p:sldIdLst></p:presentation>",
            )
            archive.writestr(
                "ppt/_rels/presentation.xml.rels",
                f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>',
            )
            for n in (1, 2, 3):
                archive.writestr(f"ppt/slides/slide{n}.xml", self._slide(f"內容{n}"))
        return path

    def test_labels_follow_presentation_order_not_file_names(self):
        with TemporaryDirectory() as tmp:
            text = classification.extract_pptx_text(self._deck(tmp, [1, 3, 2]))
        self.assertEqual(text.split("\n\n"), ["[投影片 1]\n內容1", "[投影片 2]\n內容3", "[投影片 3]\n內容2"])

    def test_unreadable_presentation_part_falls_back_to_file_order(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.pptx"
            with zipfile.ZipFile(path, "w") as archive:
                for n in (2, 1):
                    archive.writestr(f"ppt/slides/slide{n}.xml", self._slide(f"內容{n}"))
            text = classification.extract_pptx_text(path)
        self.assertEqual(text.split("\n\n"), ["[投影片 1]\n內容1", "[投影片 2]\n內容2"])


if __name__ == "__main__":
    unittest.main()
