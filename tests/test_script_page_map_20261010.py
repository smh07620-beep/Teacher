import unittest
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / "static" / "teacher-media-script-1014.js").read_text(encoding="utf-8")


class ScriptPageMapTest(unittest.TestCase):
    def test_editor_has_page_map_panel_and_warning(self):
        self.assertIn('id="teacher-script-pagemap-1040"', JS)
        self.assertIn("paintPageMap1040", JS)
        self.assertIn("一頁一段", JS)
        self.assertIn("游標目前在", JS)
        self.assertIn("沒有對應講稿", JS)


if __name__ == "__main__":
    unittest.main()
