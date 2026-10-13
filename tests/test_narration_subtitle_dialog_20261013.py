"""老師旁白字幕（2026-10-13）：在旁白那一列直接產生草稿、校對、核准。

原本字幕區只能從「影片畫面來源」選教材，選不到旁白錄音，老師按完成後也看不到任何字幕進度。
"""
import unittest
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "static" / "admin-course-material.js").read_text(encoding="utf-8")


class NarrationSubtitleDialogTests(unittest.TestCase):
    def test_button_only_for_teacher_narration_and_sits_in_both_row_layouts(self):
        body = SOURCE[SOURCE.index("function adminMaterialNarrationSubtitleButton"):SOURCE.index("function ensureNarrationSubtitleDialog")]
        self.assertIn("teacher_narration", body)
        self.assertIn("data-narration-subtitle=", body)
        row = SOURCE[SOURCE.index("function adminHubMaterialRow"):SOURCE.index("// 老師旁白的字幕")]
        self.assertEqual(row.count("${adminMaterialNarrationSubtitleButton(m)}"), 2)

    def test_dialog_uses_existing_subtitle_apis(self):
        body = SOURCE[SOURCE.index("function ensureNarrationSubtitleDialog"):SOURCE.index("function bindNarrationSubtitleControls")]
        self.assertIn("/api/media-subtitles?materialId=", body)
        self.assertIn("/api/media-subtitles/generate", body)
        self.assertIn("/api/media-subtitles/jobs/", body)
        self.assertIn("method:'PATCH'", body)
        self.assertIn("status==='approved'", body)

    def test_approval_is_explicit_and_not_automatic(self):
        body = SOURCE[SOURCE.index("function ensureNarrationSubtitleDialog"):SOURCE.index("function bindNarrationSubtitleControls")]
        self.assertIn("save('approved')", body)
        self.assertIn("草稿不會自動公開", body)

    def test_no_inline_handlers_and_controls_are_bound(self):
        body = SOURCE[SOURCE.index("function adminMaterialNarrationSubtitleButton"):SOURCE.index("function ensureMaterialPurgeDialog")]
        self.assertNotIn("onclick=", body)
        self.assertIn("bindNarrationSubtitleControls(box);", SOURCE[SOURCE.index("function paintAdminCourseMaterialHub"):][:500])


if __name__ == "__main__":
    unittest.main()
