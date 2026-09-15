"""6.8.1 safety regressions for Office preview completion."""
import unittest
from pathlib import Path


ROOT=Path(__file__).parents[1]


class OfficePreview681Tests(unittest.TestCase):
    def test_worker_uses_original_extension_not_source_bin(self):
        source=ROOT.joinpath("material_worker.py").read_text(encoding="utf-8")
        self.assertIn('source=temp/("source"+Path(original).suffix.lower())',source)
        self.assertIn("Office/PDF preview 產生失敗，不能完成工作",source)

    def test_zero_page_office_cannot_be_committed(self):
        source=ROOT.joinpath("app.py").read_text(encoding="utf-8")
        self.assertIn("Office/PDF 必須有有效 preview.pdf 與 pageCount 才能完成",source)

    def test_learner_office_view_does_not_fallback_to_original(self):
        source=ROOT.joinpath("app.py").read_text(encoding="utf-8")
        self.assertIn('if entry.get("viewerMode") == "slides" or int(entry.get("pageCount", 0) or 0) > 0:',source)
        self.assertIn("abort(403)",source)

