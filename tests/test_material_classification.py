import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from teacher_app.materials import classification


class _GroqResponse:
    def __init__(self, payload, *, ok=True):
        self._payload = payload
        self.ok = ok

    def json(self):
        return self._payload


class MaterialTextExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_clean_and_plain_text_preserve_legacy_normalization_and_encodings(self):
        self.assertEqual(
            classification.clean_extracted_text("  A\t B\x00\n\n\n\nC  "),
            "A B\n\nC",
        )
        path = self.root / "notes.txt"
        path.write_bytes("血液檢驗流程".encode("cp950"))
        self.assertEqual(classification.extract_plain_text(path), "血液檢驗流程")

    def test_pptx_text_is_sorted_and_labeled_like_legacy(self):
        path = self.root / "deck.pptx"
        slide = (
            "<?xml version='1.0'?><p:sld xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main' "
            "xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'><p:cSld><a:t>{}</a:t></p:cSld></p:sld>"
        )
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("ppt/slides/slide2.xml", slide.format("第二頁"))
            archive.writestr("ppt/slides/slide1.xml", slide.format("第一頁"))
        self.assertEqual(
            classification.extract_pptx_text(path),
            "[投影片 1]\n第一頁\n\n[投影片 2]\n第二頁",
        )

    def test_docx_text_joins_runs_and_paragraphs_like_legacy(self):
        path = self.root / "document.docx"
        document = """<?xml version='1.0'?>
        <w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>
          <w:body>
            <w:p><w:r><w:t>標準</w:t></w:r><w:r><w:t>作業</w:t></w:r></w:p>
            <w:p><w:r><w:t>第二段</w:t></w:r></w:p>
          </w:body>
        </w:document>"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", document)
        self.assertEqual(classification.extract_docx_text(path), "標準作業\n第二段")

    def test_pdf_text_preserves_page_labels_and_optional_pymupdf_failure_shape(self):
        class Page:
            def __init__(self, text):
                self.text = text

            def get_text(self, mode):
                self.mode = mode
                return self.text

        class Document(list):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        fake = SimpleNamespace(open=lambda _path: Document([Page("A  B"), Page(""), Page("C")]))
        with mock.patch.object(classification, "pymupdf", fake):
            self.assertEqual(
                classification.extract_pdf_text(self.root / "x.pdf"),
                "[第 1 頁]\nA B\n\n[第 3 頁]\nC",
            )
        with mock.patch.object(classification, "pymupdf", None):
            with self.assertRaisesRegex(RuntimeError, "伺服器缺少 PyMuPDF，無法擷取 PDF 文字。"):
                classification.extract_pdf_text(self.root / "x.pdf")

    def test_office_to_pdf_uses_same_soffice_contract_timeout_and_error_message(self):
        source = self.root / "sheet.xlsx"
        source.write_bytes(b"office")
        temp_root = self.root / "convert"

        def successful_run(command, **kwargs):
            out_dir = Path(command[command.index("--outdir") + 1])
            (out_dir / "sheet.pdf").write_bytes(b"%PDF")
            self.assertEqual(kwargs["timeout"], 180)
            self.assertFalse(kwargs["check"])
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        with mock.patch.dict(os.environ, {"SOFFICE_PATH": "custom-soffice"}), mock.patch.object(
            classification.subprocess, "run", side_effect=successful_run
        ) as run:
            result = classification.convert_office_to_pdf_for_text(source, temp_root)
        self.assertEqual(result.name, "sheet.pdf")
        self.assertEqual(run.call_args.args[0][0], "custom-soffice")

        failure_root = self.root / "failed"
        with mock.patch.object(
            classification.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=1, stdout=b"", stderr="轉檔錯誤".encode("utf-8")),
        ):
            with self.assertRaisesRegex(RuntimeError, "LibreOffice 無法將教材轉成可讀文字的 PDF：轉檔錯誤"):
                classification.convert_office_to_pdf_for_text(source, failure_root)

    def test_local_classification_extraction_is_best_effort_and_bounded(self):
        path = self.root / "notes.txt"
        path.write_text("A" * 20000, encoding="utf-8")
        self.assertEqual(len(classification.extract_local_text_for_classification(path)), 14000)
        with mock.patch.object(classification, "extract_pdf_text", side_effect=RuntimeError("broken")):
            self.assertEqual(
                classification.extract_local_text_for_classification(self.root / "broken.pdf"),
                "",
            )


class MaterialClassificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_keyword_scoring_caps_repeats_and_merges(self):
        scores = classification.score_material_classification("故障 故障 故障 故障 故障", 2)
        self.assertEqual(scores["troubleshooting"], 8)
        merged = classification.merge_classification_scores(
            {"sop": 4, "unknown": 99},
            {"sop": 3, "atlas": 2},
        )
        self.assertEqual(merged["sop"], 7)
        self.assertEqual(merged["atlas"], 2)
        self.assertNotIn("unknown", merged)

    def test_extension_image_title_content_and_default_results_match_legacy(self):
        video = classification.classify_uploaded_material(self.root / "clip.srt", "clip.srt")
        self.assertEqual(video, ("video", "副檔名判斷", "影音/字幕檔自動放入操作教學影片區"))

        image = classification.classify_uploaded_material(self.root / "atlas.png", "atlas.png")
        self.assertEqual(image, ("atlas", "檔名判斷", "檔名符合 atlas 特徵"))

        title = classification.classify_uploaded_material(
            self.root / "manual.docx",
            "SOP_標準作業_作業指引.docx",
        )
        self.assertEqual(title, ("sop", "檔名判斷", "檔名關鍵字分數 12"))

        content = classification.classify_uploaded_material(
            self.root / "notes.txt",
            "notes.txt",
            text_override="故障 故障 異常 異常 排除 排除 error error",
        )
        self.assertEqual(content, ("troubleshooting", "內容規則判斷", "關鍵字分數 8"))

        with mock.patch.object(classification, "groq_classify_material", return_value=("", "")):
            default = classification.classify_uploaded_material(
                self.root / "notes.txt",
                "notes.txt",
                text_override="一般核心教育內容",
            )
        self.assertEqual(default, ("standard", "預設分類", "內容未呈現足夠明確的專用模組特徵"))

    def test_groq_free_classifier_preserves_default_model_timeout_payload_and_reason(self):
        payload = {
            "choices": [
                {"message": {"content": json.dumps({"materialType": "case", "reason": "案例脈絡明確"}, ensure_ascii=False)}}
            ]
        }
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "secret"}, clear=True), mock.patch.object(
            classification.requests, "post", return_value=_GroqResponse(payload)
        ) as post:
            result = classification.groq_classify_material("一般教材內容" * 20, "case.pdf", "案例", "說明")
        self.assertEqual(result, ("case", "案例脈絡明確"))
        self.assertEqual(post.call_args.kwargs["timeout"], 12)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "qwen/qwen3.6-27b")
        self.assertEqual(post.call_args.kwargs["json"]["temperature"], 0.0)
        self.assertEqual(post.call_args.kwargs["json"]["max_completion_tokens"], 250)
        self.assertEqual(post.call_args.kwargs["json"]["response_format"], {"type": "json_object"})

    def test_groq_timeout_clamp_and_failures_fall_back_silently(self):
        with mock.patch.dict(
            os.environ,
            {"GROQ_API_KEY": "secret", "GROQ_MODEL": "custom-model", "AI_CLASSIFY_TIMEOUT_SECONDS": "99"},
            clear=True,
        ), mock.patch.object(
            classification.requests,
            "post",
            return_value=_GroqResponse({}, ok=False),
        ) as post:
            self.assertEqual(classification.groq_classify_material("x" * 120, "x.pdf", "", ""), ("", ""))
        self.assertEqual(post.call_args.kwargs["timeout"], 30)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "custom-model")

        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "secret", "AI_CLASSIFY_TIMEOUT_SECONDS": "bad"}, clear=True):
            self.assertEqual(classification.classify_timeout_seconds(), 12)
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(classification.requests, "post") as post:
            self.assertEqual(classification.groq_classify_material("x" * 120, "x.pdf", "", ""), ("", ""))
            post.assert_not_called()

    def test_classify_uses_groq_only_after_rules_are_inconclusive(self):
        with mock.patch.object(
            classification,
            "groq_classify_material",
            return_value=("case", "內容呈現案例分析"),
        ) as groq:
            result = classification.classify_uploaded_material(
                self.root / "lesson.txt",
                "lesson.txt",
                title="一般教材",
                text_override="這是一份沒有明顯關鍵字但具有足夠長度的教學內容。" * 8,
            )
        self.assertEqual(result, ("case", "Groq AI 內容判斷", "內容呈現案例分析"))
        groq.assert_called_once()

    def test_module_has_no_legacy_host_or_question_generation_ownership(self):
        source = Path(classification.__file__).read_text(encoding="utf-8")
        self.assertNotIn("legacy_host", source)
        for forbidden in (
            "AI_MAX_QUESTIONS",
            "AI_SOURCE_MAX_CHARS",
            "generate_ai",
            "question_repository",
            "assessment_repository",
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
