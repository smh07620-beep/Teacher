import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ClinicalAuthoringIntegration20261006Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.atlas_js = ROOT.joinpath("static", "atlas-docx-wizard-70.js").read_text(encoding="utf-8")
        cls.teacher = ROOT.joinpath("static", "teacher-content-studio-71.js").read_text(encoding="utf-8")
        cls.interface = ROOT.joinpath("static", "teacher-interface-convergence-1014.js").read_text(encoding="utf-8")
        cls.system_html = ROOT.joinpath("static", "system.html").read_text(encoding="utf-8")
        cls.importer = ROOT.joinpath("teacher_app", "atlas", "importer.py").read_text(encoding="utf-8")
        cls.atlas_routes = ROOT.joinpath("teacher_app", "atlas", "routes.py").read_text(encoding="utf-8")
        cls.ppt_storage = ROOT.joinpath("teacher_app", "materials", "ai_presentation_storage.py").read_text(encoding="utf-8")
        cls.ppt_runtime = ROOT.joinpath("teacher_app", "materials", "ai_presentation_runtime.py").read_text(encoding="utf-8")
        cls.ai_material = ROOT.joinpath("static", "teacher-ai-material-1014.js").read_text(encoding="utf-8")
        cls.script_runtime = ROOT.joinpath("teacher_app", "materials", "media_script_runtime.py").read_text(encoding="utf-8")

    def test_docx_picker_accepts_array_shaped_admin_material_response(self):
        self.assertIn("const list=Array.isArray(data)?data:(data.slides||data.materials||[])", self.atlas_js)
        self.assertIn("item.filename||item.storageFilename", self.atlas_js)
        self.assertIn("box.querySelector('#atlas-docx-source')", self.atlas_js)

    def test_word_atlas_import_lives_in_teacher_workspace_not_learner_header(self):
        # Single entry point: the course wizard.  The studio no longer hosts its own Word -> Atlas workspace.
        self.assertNotIn("openTeacherAtlasDocxWorkspace", self.teacher)
        self.assertNotIn("atlas-docx", self.teacher)
        self.assertNotIn("openAtlasCreate", self.teacher)
        self.assertNotIn("Word → 圖譜", self.interface)
        self.assertNotIn('id="atlas-create-action"', self.system_html)
        self.assertNotIn('id="atlas-import-action"', self.system_html)

    def test_atlas_docx_can_materialize_remote_r2_or_mega_source(self):
        self.assertIn("def materialize_docx_source(", self.importer)
        self.assertIn("ai_runtime.material_source_to_temp", self.importer)
        self.assertIn("paths_provider=current_paths", self.atlas_routes)

    def test_ai_powerpoint_legacy_mega_setting_prefers_configured_r2(self):
        self.assertIn("AI_PRESENTATION_FALLBACK_TO_R2", self.ppt_storage)
        self.assertIn('requested == "mega"', self.ppt_storage)
        self.assertIn('return "r2"', self.ppt_storage)
        self.assertIn("TEMPLATE_PROVIDER_FALLBACK", self.ppt_runtime)

    def test_ai_multi_source_drafting_keeps_readable_sources_and_reports_failures(self):
        self.assertIn("source_warnings = []", self.script_runtime)
        self.assertIn('"sourceWarnings": source_warnings', self.script_runtime)
        self.assertIn("所選教材都沒有可用的文字來源", self.script_runtime)
        self.assertIn("部分來源未能讀取", self.ai_material)
        self.assertIn("backendRank = {r2:0,oci:1,gdrive:2,mega:3,local:4}", self.ai_material)


if __name__ == "__main__":
    unittest.main()
