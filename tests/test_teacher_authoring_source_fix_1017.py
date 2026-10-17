import unittest
from pathlib import Path

from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class TeacherAuthoringSourceFix1017Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT.joinpath("static", "teacher-media-subtitle-1014.js").read_text(encoding="utf-8")  # picker merged into its owner 2026-10-17
        cls.subtitle_frontend = ROOT.joinpath("static", "teacher-media-subtitle-1014.js").read_text(encoding="utf-8")
        cls.subtitle_routes = ROOT.joinpath("teacher_app", "materials", "media_subtitle_routes.py").read_text(encoding="utf-8")
        cls.presentation_routes = ROOT.joinpath("teacher_app", "materials", "ai_presentation_routes.py").read_text(encoding="utf-8")

    def test_hotfix_file_is_merged_into_the_subtitle_owner(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertNotIn("/teacher-authoring-source-fix-1017.js", body)
        self.assertFalse(ROOT.joinpath("static", "teacher-authoring-source-fix-1017.js").exists())
        self.assertIn("/teacher-media-subtitle-1014.js", body)

    def test_powerpoint_is_one_guided_studio_without_visible_internal_ids(self):
        presentation = ROOT.joinpath("static", "teacher-ai-presentation-1016.js").read_text(encoding="utf-8")
        material = ROOT.joinpath("static", "teacher-ai-material-1014.js").read_text(encoding="utf-8")
        for marker in (
            "AI 投影片製作室",
            "teacher-ai-material-presentation-stage-1014",
            "teacher-ai-material-draft-selected",
            "第 4 步｜選擇投影片版型（可以不選）",
            "第 5 步｜建立投影片",
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

    def test_powerpoint_authoring_mount_prefers_stable_media_workspace(self):
        material = ROOT.joinpath("static", "teacher-ai-material-1014.js").read_text(encoding="utf-8")
        self.assertIn("teacher-media-panel-presentation-1018", material)
        self.assertIn("teacher-media-production-1014", material)
        self.assertLess(
            material.index("teacher-media-production-1014"),
            material.index("admin-course-material-hub"),
        )

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
            "buildSourcePicker",
            "/api/slides/admin",
        ):
            self.assertIn(marker, self.source)
        self.assertIn("/api/media-subtitles", self.subtitle_frontend)
        self.assertIn("denied = _scope(owner", self.subtitle_routes)
        self.assertIn('action="media.subtitle.generate"', self.subtitle_routes)

    def test_media_workspace_is_opened_by_its_owner(self):
        workspace = ROOT.joinpath("static", "teacher-workspace-1014.js").read_text(encoding="utf-8")
        self.assertIn("if (state.mode === 'media') {", workspace)
        self.assertIn("await openMedia();", workspace)

    def test_fix_does_not_reintroduce_browser_admin_secrets(self):
        self.assertNotIn("getAdminKey", self.source)
        self.assertNotIn("X-Admin-Key", self.source)
        self.assertIn("credentials:'same-origin'", self.source.replace(' ', ''))



class StudioPlainLanguageAndHandoffTests(unittest.TestCase):
    PRESENTATION = ROOT.joinpath("static", "teacher-ai-presentation-1016.js").read_text(encoding="utf-8")
    MATERIAL = ROOT.joinpath("static", "teacher-ai-material-1014.js").read_text(encoding="utf-8")

    def test_no_engineer_labels_are_shown_to_teachers(self):
        for word in ("F5", "Phase 4 品質檢查", "PPTX 產生", "AI Worker 在線", "presentation family", "品質 gate", "Step 4", "Step 5", "Step 6"):
            with self.subTest(word=word):
                visible = self.PRESENTATION.split("*/", 2)[-1]
                self.assertNotIn(word, visible)

    def test_build_status_is_shown_right_under_the_build_button(self):
        build = self.PRESENTATION.index("teacher-ai-presentation-generate-1016\" type=\"button\"")
        status = self.PRESENTATION.index("id=\"teacher-ai-presentation-status-1016\"")
        step6 = self.PRESENTATION.index("第 6 步")
        self.assertLess(build, status)
        self.assertLess(status, step6)

    def test_studio_asks_the_outline_editor_for_the_approved_draft(self):
        self.assertIn("teacher-ai-material-request-draft", self.PRESENTATION)
        self.assertIn("teacher-ai-material-request-draft", self.MATERIAL)



class QualityCheckPlainTextTests(unittest.TestCase):
    SRC = ROOT.joinpath("static", "teacher-ai-presentation-1016.js").read_text(encoding="utf-8")

    def test_quality_result_is_not_raw_json(self):
        self.assertNotIn("JSON.stringify({quality", self.SRC)
        self.assertIn("qualityText(data)", self.SRC)

    def test_every_server_quality_code_has_a_plain_sentence(self):
        import sys
        sys.path.insert(0, str(ROOT))
        from teacher_app.materials.ai_presentation_quality import _QUALITY_CODES
        for code in _QUALITY_CODES:
            with self.subTest(code=code):
                self.assertIn(f"{code}:'", self.SRC)


if __name__ == "__main__":
    unittest.main()
