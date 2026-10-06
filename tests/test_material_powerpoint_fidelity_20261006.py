import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MaterialPowerPointFidelity20261006Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker = ROOT.joinpath("material_worker.py").read_text(encoding="utf-8")
        cls.renderer = ROOT.joinpath("teacher_app", "materials", "ai_video_renderer.py").read_text(encoding="utf-8")
        cls.env = ROOT.joinpath(".local-worker.env.example").read_text(encoding="utf-8")

    def test_material_worker_prefers_powerpoint_com_for_ppt_preview_fidelity(self):
        self.assertIn("ai_video_renderer.export_powerpoint_pdf", self.worker)
        self.assertIn('MATERIAL_POWERPOINT_COM_PREVIEW_ENABLED', self.worker)
        self.assertIn('"presentationRenderer":"powerpoint-com"', self.worker)
        self.assertIn('"presentationFidelity":"exact"', self.worker)
        self.assertIn("PowerPoint 原生轉檔完成", self.worker)

    def test_slide_decks_do_not_use_single_pdf_preview_path(self):
        self.assertIn('presentation_ext={".ppt",".pptx",".odp"}', self.worker)
        single_line = next(line for line in self.worker.splitlines() if line.strip().startswith("single=bool("))
        self.assertIn("ext not in presentation_ext", single_line)
        self.assertIn("STORAGE.convert_pdf_to_images", self.worker)

    def test_powerpoint_com_has_bounded_pdf_export_and_libreoffice_fallback(self):
        self.assertIn("def export_powerpoint_pdf(", self.renderer)
        self.assertIn("ExportAsFixedFormat($OutputPath,2)", self.renderer)
        self.assertIn("timeout=max(15,min(240", self.worker)
        self.assertIn("改用 LibreOffice 相容轉檔", self.worker)
        self.assertIn("STORAGE.prepare_office_pdf", self.worker)

    def test_local_worker_example_exposes_preview_fidelity_switch(self):
        self.assertIn("MATERIAL_POWERPOINT_COM_PREVIEW_ENABLED=true", self.env)
        self.assertIn("MATERIAL_POWERPOINT_COM_TIMEOUT_SECONDS=60", self.env)


if __name__ == "__main__":
    unittest.main()
