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

    def test_powerpoint_is_one_guided_studio_without_visible_internal_ids(self):
        presentation = ROOT.joinpath("static", "teacher-ai-presentation-1016.js").read_text(encoding="utf-8")
        material = ROOT.joinpath("static", "teacher-ai-material-1014.js").read_text(encoding="utf-8")
        for marker in (
            "AI PowerPoint 製作室",
            "teacher-ai-material-presentation-stage-1014",
            "teacher-ai-material-draft-selected",
            "Step 4｜選擇 PowerPoint 範本",
            "Step 5｜建立 PowerPoint",
            "teacher-ai-presentation-publication-material-1016",
            "selectedDraft.status !== 'approved'",
            "/api/ai-presentations/generate",
        ):
            self.assertIn(marker, presentation + material)
        self.assertNotIn('placeholder="aidraft-', presentation)
        self.assertNotIn('placeholder="mat-', presentation)
        self.assertNotIn("replaceInputWithSelect('teacher-ai-presentation", self.source)
        self.assertIn('draft.get("draftType") != "slides"', self.presentation_routes)
        self.assertIn('draft.get("status") != "approved"', self.presentation_routes)

    def test_powerpoint_multi_source_picker_uses_teacher_scope(self):
        material = ROOT.joinpath("static", "teacher-ai-material-1014.js").read_text(encoding="utf-8")
        self.assertIn("R.user?.preferredGroup", material)
        self.assertIn("R.user?.preferredArea", material)
        self.assertIn("String(item.group) === String(group)", material)
        self.assertIn("String(item.area) === String(area)", material)
        self.assertIn("referenceMaterialIds", material)

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
