import unittest
from pathlib import Path


ROOT=Path(__file__).parents[1]


class TeacherMediaDirectPowerPoint1026Tests(unittest.TestCase):
    def test_media_studio_does_not_duplicate_powerpoint_authoring_entry(self):
        source=ROOT.joinpath("static","teacher-ai-media-studio-1018.js").read_text(encoding="utf-8")
        video=ROOT.joinpath("static","teacher-ai-video-1015.js").read_text(encoding="utf-8")
        self.assertNotIn('id="teacher-media-direct-powerpoint-1026"',source)
        self.assertNotIn('id="teacher-ai-video-powerpoint-author-1027"',video)
        self.assertIn("來源教材／來源內容",source)
        self.assertIn("加入 PDF／Word／圖片／文字",video)
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
