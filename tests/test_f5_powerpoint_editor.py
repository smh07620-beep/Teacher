import unittest
from pathlib import Path


ROOT=Path(__file__).parents[1]


class F5PowerPointEditorTests(unittest.TestCase):
    def test_editor_uses_immutable_patch_revision_contract(self):
        source=ROOT.joinpath("static","teacher-ai-presentation-editor-f5.js").read_text(encoding="utf-8")
        self.assertIn("教師投影片編輯器",source)
        self.assertIn("儲存為新 revision 並重新產檔",source)
        self.assertIn("method:'PATCH'",source)
        self.assertIn("speakerNotes",source)
        self.assertIn("bullets",source)
        self.assertIn("layout",source)
        self.assertIn("blocks:Array.isArray(prior.blocks)?prior.blocks:[]",source)

    def test_editor_never_overwrites_old_artifact_in_browser(self):
        source=ROOT.joinpath("static","teacher-ai-presentation-editor-f5.js").read_text(encoding="utf-8")
        self.assertIn("舊版本仍完整保留",source)
        self.assertNotIn("artifactStorageKey=",source)

    def test_editor_asset_loads_after_powerpoint_workspace(self):
        source=ROOT.joinpath("teacher_app","frontend","assets.py").read_text(encoding="utf-8")
        base=source.index('"/teacher-ai-presentation-1016.js"')
        editor=source.index('"/teacher-ai-presentation-editor-f5.js"')
        self.assertLess(base,editor)

    def test_editor_can_fill_speaker_notes_from_approved_script(self):
        source=ROOT.joinpath("static","teacher-ai-presentation-editor-f5.js").read_text(encoding="utf-8")
        self.assertIn("/api/media-scripts?materialId=",source)
        self.assertIn("item.status==='approved'",source)
        self.assertIn("依內容自動分段",source)
        self.assertIn("/api/ai-presentations/align-script",source)
        # 只改瀏覽器內的備註；儲存仍走既有 PATCH，不另開寫入路徑。
        self.assertEqual(source.count("method:'PATCH'"),1)

    def test_script_prompt_asks_for_paragraphs_and_normal_speaking_pace(self):
        source=ROOT.joinpath("teacher_app","materials","media_script_runtime.py").read_text(encoding="utf-8")
        self.assertIn("每分鐘約 280 字",source)
        self.assertIn("用空行把講稿分成多個段落",source)


if __name__=="__main__":
    unittest.main()
