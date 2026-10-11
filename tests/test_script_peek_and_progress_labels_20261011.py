"""講稿旁投影片預覽、閱讀進度改為頁數顯示 (2026-10-11)。"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ScriptPeekTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "teacher-media-script-1014.js").read_text(encoding="utf-8")

    def test_editor_has_sticky_slide_preview_next_to_the_script(self):
        for marker in ("teacher-script-split-1041", "teacher-script-peek-1041", "teacher-script-peek-strip-1041", "lg:sticky"):
            self.assertIn(marker, self.source)

    def test_preview_follows_cursor_and_thumbnails_jump_to_paragraph(self):
        for marker in ("paintPeek1041(cursorIndex", "jumpToParagraph1041", "data-peek-page", "data-peek-step"):
            self.assertIn(marker, self.source)

    def test_preview_uses_the_same_page_sources_as_the_reader(self):
        self.assertIn("/material-preview/", self.source)
        self.assertIn("slide-${String(page).padStart(2, '0')}", self.source)


class ProgressLabelTests(unittest.TestCase):
    def test_document_progress_reports_pages_not_percent(self):
        source = (ROOT / "static" / "learner-reading-progress-f2.js").read_text(encoding="utf-8")
        self.assertIn("'已讀 '+pages.read+'／'+pages.total+' 頁'", source)
        self.assertNotIn("'已完成 '+Math.round(pct)+'%'", source)
        self.assertNotIn("'繼續閱讀 · '", source)

    def test_next_action_label_has_no_percentage(self):
        source = (ROOT / "teacher_app" / "command_center" / "service.py").read_text(encoding="utf-8")
        self.assertNotIn('繼續閱讀 {', source)


if __name__ == "__main__":
    unittest.main()
