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


if __name__=="__main__":
    unittest.main()
