"""6.8.1 safety regressions for Office preview completion."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import material_worker


ROOT=Path(__file__).parents[1]


class OfficePreview681Tests(unittest.TestCase):
    def test_worker_uses_original_extension_not_source_bin(self):
        source=ROOT.joinpath("material_worker.py").read_text(encoding="utf-8")
        self.assertIn('source=temp/("source"+Path(original).suffix.lower())',source)
        self.assertIn("Office/PDF preview 產生失敗，不能完成工作",source)

    def test_zero_page_office_cannot_be_committed(self):
        source=ROOT.joinpath("teacher_app/materials/job_commit.py").read_text(encoding="utf-8")
        self.assertIn("Office/PDF 必須有有效 preview.pdf 與 pageCount 才能完成",source)

    def test_learner_office_view_does_not_fallback_to_original(self):
        source=ROOT.joinpath("teacher_app/materials/delivery_routes.py").read_text(encoding="utf-8")
        self.assertIn('if entry.get("viewerMode") == "slides" or int(entry.get("pageCount", 0) or 0) > 0:',source)
        self.assertIn("abort(403)",source)

    def test_worker_builds_reusable_text_index_sidecar(self):
        with tempfile.TemporaryDirectory() as temp_name:
            temp=Path(temp_name)
            source=temp/"lesson.pdf"
            source.write_bytes(b"%PDF fixture")
            with patch.object(
                material_worker.classification,
                "extract_pdf_text",
                return_value="[第 1 頁]\n教材全文 " * 30,
            ):
                index,meta=material_worker._build_text_index(source,temp)
            self.assertTrue(index.is_file())
            self.assertIn("教材全文",index.read_text(encoding="utf-8"))
            self.assertTrue(meta["textIndexAvailable"])
            self.assertGreater(meta["textIndexChars"],80)
