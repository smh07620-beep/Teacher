import unittest
from pathlib import Path


ROOT=Path(__file__).parents[1]


class TeacherMediaDirectPowerPoint1026Tests(unittest.TestCase):
    def test_media_studio_has_first_class_direct_file_powerpoint_entry(self):
        source=ROOT.joinpath("static","teacher-ai-media-studio-1018.js").read_text(encoding="utf-8")
        self.assertIn("teacher-media-direct-powerpoint-1026",source)
        self.assertIn("AI POWERPOINT",source)
        self.assertIn("AI PowerPoint 製作",source)
        self.assertIn("PowerPoint 保留單一入口",source)
        self.assertIn("PDF／Word／圖片／文字",source)
        self.assertNotIn("teacher-media-open-powerpoint-1018",source)

    def test_controls_export_single_powerpoint_list_owner(self):
        source=ROOT.joinpath("static","teacher-ai-media-controls-1023.js").read_text(encoding="utf-8")
        self.assertIn("refreshVideoPresentations",source)
        self.assertIn("presentationRefreshPromise",source)
        self.assertIn("presentationRefreshController",source)
        self.assertIn("讀取所有已核准 PowerPoint",source)
        self.assertIn("/api/ai-presentations",source)

    def test_authoring_workspace_still_accepts_multiple_arbitrary_files(self):
        source=ROOT.joinpath("static","teacher-ai-material-1014.js").read_text(encoding="utf-8")
        self.assertIn('id="teacher-ai-material-file-1014" type="file" multiple',source)
        for extension in (".pdf",".docx",".xlsx",".pptx",".png",".txt"):
            self.assertIn(extension,source)
        self.assertIn("authoring source",source)


if __name__=="__main__":
    unittest.main()
