"""Course wizard step 3 offers a direct "用圖譜出題" entry (atlas_hotspot questions)."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "static"


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


class CourseWizardAtlasExamModeTest(unittest.TestCase):
    def test_step_three_lists_atlas_mode(self):
        src = read("course-wizard-681.js")
        self.assertIn("atlas:{label:'🔬 用圖譜出題'", src)
        self.assertIn("const primary=['later','bank','ai','atlas'];", src)
        self.assertIn("state.examMode==='atlas'?'🔬 開啟圖譜出題'", src)

    def test_studio_opens_manual_editor_on_hotspot_type(self):
        studio = read("teacher-content-studio-71.js")
        self.assertIn("openManual(catId,mode==='atlas'?'atlas_hotspot':'choice')", studio)
        panels = read("teacher-content-tool-panels-710.js")
        self.assertIn("'atlas_hotspot'?'atlas_hotspot'", panels.replace("(preset==='atlas'||preset==='atlas_hotspot')", "'atlas_hotspot'"))
        self.assertIn("['question','image','video','atlas']", panels)

    def test_manual_form_offers_hotspot_option(self):
        self.assertIn('value="atlas_hotspot"', read("admin-question-bank.js"))

    def test_atlas_import_next_step_requests_atlas_mode(self):
        self.assertIn("courseWizard681OpenAssessmentAuthoring('atlas')", read("atlas-docx-wizard-70.js"))


if __name__ == "__main__":
    unittest.main()
