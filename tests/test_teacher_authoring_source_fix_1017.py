import unittest
from pathlib import Path

from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class TeacherAuthoringSourceFix1017Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT.joinpath("static", "teacher-authoring-source-fix-1017.js").read_text(encoding="utf-8")
        cls.subtitle_frontend = ROOT.joinpath("static", "teacher-media-subtitle-1014.js").read_text(encoding="utf-8")
        cls.subtitle_routes = ROOT.joinpath("teacher_app", "materials", "media_subtitle_routes.py").read_text(encoding="utf-8")
        cls.presentation_routes = ROOT.joinpath("teacher_app", "materials", "ai_presentation_routes.py").read_text(encoding="utf-8")

    def test_asset_loads_after_interface_convergence(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertIn("/teacher-authoring-source-fix-1017.js", body)
        self.assertLess(
            body.index("/teacher-interface-convergence-1014.js"),
            body.index("/teacher-authoring-source-fix-1017.js"),
        )

    def test_powerpoint_uses_material_and_approved_outline_pickers(self):
        for marker in (
            "replaceInputWithSelect('teacher-ai-presentation-material-1016')",
            "replaceInputWithSelect('teacher-ai-presentation-draft-1016')",
            "來源教材",
            "已核准投影片大綱",
            "/api/ai-material-drafts?materialId=",
            "item?.draftType === 'slides'",
            "item?.status === 'approved'",
        ):
            self.assertIn(marker, self.source)
        self.assertIn('draft.get("draftType") != "slides"', self.presentation_routes)
        self.assertIn('draft.get("status") != "approved"', self.presentation_routes)

    def test_subtitle_has_its_own_visible_media_picker(self):
        for marker in (
            "teacher-subtitle-material-1017",
            "來源影音教材",
            "isCaptionMaterial",
            "syncSubtitleSource",
            "/api/slides/admin",
        ):
            self.assertIn(marker, self.source)
        self.assertIn("/api/media-subtitles", self.subtitle_frontend)
        self.assertIn("denied = _scope(owner", self.subtitle_routes)
        self.assertIn('action="media.subtitle.generate"', self.subtitle_routes)

    def test_media_workspace_has_failure_recovery(self):
        for marker in (
            "safeOpenMediaWorkspace",
            "fallbackRevealMediaWorkspace",
            "teacher-course-media-entry-1014 button",
            "teacherMode', 'media'",
        ):
            self.assertIn(marker, self.source)

    def test_fix_does_not_reintroduce_browser_admin_secrets(self):
        self.assertNotIn("getAdminKey", self.source)
        self.assertNotIn("X-Admin-Key", self.source)
        self.assertIn("credentials:'same-origin'", self.source)


if __name__ == "__main__":
    unittest.main()
