import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MaterialPowerPointFidelity20261006Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker = ROOT.joinpath("material_worker.py").read_text(encoding="utf-8")
        cls.renderer = ROOT.joinpath("teacher_app", "materials", "ai_video_renderer.py").read_text(encoding="utf-8")
        cls.env = ROOT.joinpath(".local-worker.env.example").read_text(encoding="utf-8")

    def test_material_worker_prefers_direct_powerpoint_frames(self):
        self.assertIn("ai_video_renderer.export_powerpoint_preview_frames", self.worker)
        self.assertIn('MATERIAL_POWERPOINT_COM_PREVIEW_ENABLED', self.worker)
        self.assertIn('MATERIAL_POWERPOINT_PREVIEW_LONG_EDGE', self.worker)
        self.assertIn('"officeConversionMode":"powerpoint-com-direct"', self.worker)
        self.assertIn('"presentationRenderer":"powerpoint-com"', self.worker)
        self.assertIn('"presentationFidelity":"exact"', self.worker)
        self.assertIn("不經 PDF/LibreOffice 重排", self.worker)

    def test_powerpoint_preview_preserves_native_slide_ratio(self):
        self.assertIn("def export_powerpoint_preview_frames(", self.renderer)
        self.assertIn("$deck.PageSetup.SlideWidth", self.renderer)
        self.assertIn("$deck.PageSetup.SlideHeight", self.renderer)
        self.assertIn("[Math]::Round($LongEdge*$slideHeight/$slideWidth)", self.renderer)
        self.assertIn("[Math]::Round($LongEdge*$slideWidth/$slideHeight)", self.renderer)
        self.assertIn("('slide-{0:D2}.png' -f $i)", self.renderer)
        self.assertIn(".Export($target,'PNG',$outW,$outH)", self.renderer)

    def test_slide_decks_do_not_use_single_pdf_preview_path(self):
        self.assertIn('presentation_ext={".ppt",".pptx",".odp"}', self.worker)
        single_line = next(line for line in self.worker.splitlines() if line.strip().startswith("single=bool("))
        self.assertIn("ext not in presentation_ext", single_line)
        self.assertIn("if direct_presentation_frames:", self.worker)
        self.assertIn("STORAGE.upload_material_tree_to_mega", self.worker)

    def test_powerpoint_com_falls_back_to_libreoffice_when_direct_export_unavailable(self):
        self.assertIn("改用 LibreOffice 相容轉檔", self.worker)
        self.assertIn("STORAGE.prepare_office_pdf", self.worker)
        self.assertIn("and not direct_presentation_frames", self.worker)

    def test_local_worker_example_exposes_preview_fidelity_controls(self):
        self.assertIn("MATERIAL_POWERPOINT_COM_PREVIEW_ENABLED=true", self.env)
        self.assertIn("MATERIAL_POWERPOINT_COM_TIMEOUT_SECONDS=60", self.env)
        self.assertIn("MATERIAL_POWERPOINT_PREVIEW_LONG_EDGE=1920", self.env)


if __name__ == "__main__":
    unittest.main()
