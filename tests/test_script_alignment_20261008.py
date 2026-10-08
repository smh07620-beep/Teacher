import unittest
from pathlib import Path

from teacher_app.materials import script_alignment as sa


def slides(*titles):
    return [{"id": f"s{i+1}", "title": t[0], "bullets": list(t[1:]), "enabled": True, "speakerNotes": ""} for i, t in enumerate(titles)]


SCRIPT = (
    "大家好，今天我們要介紹血液抹片的製作流程。\n\n"
    "第一步是採檢與抗凝劑。EDTA 管要充分混勻，避免凝固影響細胞形態。\n\n"
    "接著是抹片製作，推片角度約三十度，速度要平穩，才能得到羽毛狀邊緣。\n\n"
    "染色使用瑞氏染劑，染色時間與緩衝液 pH 值會影響細胞顏色。\n\n"
    "最後是顯微鏡判讀，先用低倍找到理想觀察區，再用油鏡計數白血球分類。\n\n"
    "※ 本講稿需由授課教師確認後方可用於正式教學影音。"
)
DECK = slides(
    ("課程介紹", "血液抹片製作流程"),
    ("採檢", "EDTA 抗凝劑", "充分混勻"),
    ("抹片製作", "推片角度", "羽毛狀邊緣"),
    ("染色", "瑞氏染劑", "緩衝液 pH"),
    ("顯微鏡判讀", "低倍找區", "油鏡計數白血球"),
)


class ScriptAlignmentTests(unittest.TestCase):
    def test_paragraphs_follow_slide_content_in_order(self):
        out = sa.align_script_to_slides(SCRIPT, DECK)
        self.assertEqual(out["mode"], "content-aligned")
        seg = out["segments"]
        self.assertEqual(len(seg), 5)
        self.assertIn("大家好", seg[0])
        self.assertIn("EDTA", seg[1])
        self.assertIn("推片", seg[2])
        self.assertIn("瑞氏", seg[3])
        self.assertIn("油鏡", seg[4])
        self.assertNotIn("※", "".join(seg), "教師確認聲明不是旁白")

    def test_more_paragraphs_than_slides_are_grouped_contiguously(self):
        deck = slides(("開場", "介紹"), ("抹片", "推片角度"), ("判讀", "油鏡"))
        out = sa.align_script_to_slides(SCRIPT, deck)
        seg = out["segments"]
        self.assertTrue(all(seg), "有足夠段落時每張都要分到內容")
        joined = "\n".join(seg)
        for needle in ("大家好", "EDTA", "推片", "瑞氏", "油鏡"):
            self.assertIn(needle, joined)
        self.assertLess(joined.index("EDTA"), joined.index("瑞氏"))

    def test_fewer_units_than_slides_leaves_extra_slides_empty(self):
        out = sa.align_script_to_slides("只有一段講稿。", slides(("甲",), ("乙",), ("丙",)))
        self.assertEqual(out["mode"], "one-per-slide")
        self.assertEqual(sum(1 for text in out["segments"] if text), 1)

    def test_empty_script_or_no_slides(self):
        self.assertEqual(sa.align_script_to_slides("", DECK)["mode"], "empty")
        self.assertEqual(sa.align_script_to_slides(SCRIPT, [])["segments"], [])

    def test_attach_does_not_overwrite_teacher_notes_and_skips_disabled(self):
        deck = slides(("採檢", "EDTA"), ("抹片", "推片"))
        deck[0]["speakerNotes"] = "老師自己寫的"
        out, info = sa.attach_script_notes(deck, SCRIPT)
        self.assertFalse(info["applied"])
        self.assertEqual(out[0]["speakerNotes"], "老師自己寫的")
        self.assertEqual(out[1]["speakerNotes"], "")
        deck = slides(("採檢", "EDTA"), ("跳過", "x"), ("抹片", "推片"))
        deck[1]["enabled"] = False
        out, info = sa.attach_script_notes(deck, SCRIPT)
        self.assertTrue(info["applied"])
        self.assertEqual(out[1]["speakerNotes"], "")
        self.assertTrue(out[0]["speakerNotes"] and out[2]["speakerNotes"])
        self.assertEqual(deck[0]["speakerNotes"], "", "不得修改傳入的原物件")

    def test_notes_are_capped_at_limit(self):
        out, info = sa.attach_script_notes(slides(("甲",)), "字" * 9000)
        self.assertEqual(len(out[0]["speakerNotes"]), sa.NOTES_LIMIT)
        self.assertEqual(info["truncated"], 1)

    def test_latest_approved_script_picks_first_approved_with_body(self):
        scripts = [{"status": "draft", "body": "x"}, {"status": "approved", "body": " "}, {"status": "approved", "body": "ok", "id": "a"}]
        self.assertEqual(sa.latest_approved_script(scripts)["id"], "a")
        self.assertIsNone(sa.latest_approved_script([{"status": "draft", "body": "x"}]))

    def test_pace_matches_generator_target(self):
        source = Path("teacher_app/materials/media_script_runtime.py").read_text(encoding="utf-8")
        self.assertIn(f"每分鐘約 {sa.CHARS_PER_MINUTE} 字", source)


class GeneratePresentationAutoNotesTests(unittest.TestCase):
    """核准的講稿會在產生 PowerPoint 時自動分到每頁備註，老師不用指定切點。"""

    def _run(self, scripts):
        from unittest.mock import MagicMock, patch
        from teacher_app.materials import ai_presentation_runtime as runtime

        draft = {"id": "d1", "draftType": "slides", "status": "approved", "approvedBy": "t", "approvedAt": "2026-10-08",
                 "group": "g", "area": "a", "materialId": "m1", "title": "血液抹片",
                 "body": "第 1 張：採檢\n- EDTA 抗凝劑\n第 2 張：抹片製作\n- 推片角度\n第 3 張：染色\n- 瑞氏染劑"}
        source = {"id": "m1", "group": "g", "area": "a", "title": "血液抹片"}
        captured = {}
        storage = MagicMock()
        storage.store.return_value = {"backend": "r2", "key": "k", "filename": "f.pptx", "sha256": "x", "byteSize": 1, "mimeType": "m"}

        def fake_render(**kwargs):
            captured["rendered"] = kwargs["slides"]
            kwargs["output_path"].write_bytes(b"x")

        with patch.object(runtime.repository, "get_presentation_by_source_job_id", return_value=None), \
             patch.object(runtime.media_script_repository, "get_script", return_value=draft), \
             patch.object(runtime.media_script_repository, "list_scripts", return_value=scripts), \
             patch.object(runtime.material_repository, "get_material", return_value=source), \
             patch.object(runtime, "_validated_template", return_value=None), \
             patch.object(runtime, "render_pptx", side_effect=fake_render), \
             patch.object(runtime.repository, "create_presentation", side_effect=lambda **kw: captured.update(saved=kw["slides"]) or {"id": "p1"}):
            runtime.generate_presentation(job={"id": "j1", "draftId": "d1", "group": "g", "area": "a", "request": {}}, storage=storage)
        return captured

    def test_approved_script_fills_notes_in_order(self):
        got = self._run([{"status": "approved", "body": "先說採檢，EDTA 要混勻。\n\n再說推片角度與抹片製作。\n\n最後講瑞氏染劑與染色。"}])
        notes = [slide["speakerNotes"] for slide in got["saved"]]
        self.assertIn("EDTA", notes[0])
        self.assertIn("推片", notes[1])
        self.assertIn("瑞氏", notes[2])
        self.assertEqual(notes, [slide["speakerNotes"] for slide in got["rendered"]], "PPTX 與保存的 revision 內容一致")

    def test_no_approved_script_keeps_notes_empty(self):
        got = self._run([{"status": "draft", "body": "還沒核准"}])
        self.assertTrue(all(slide["speakerNotes"] == "" for slide in got["saved"]))


if __name__ == "__main__":
    unittest.main()
