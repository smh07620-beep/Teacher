from pathlib import Path
import unittest

from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class TeacherMediaAudio1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "teacher-media-audio-1014.js").read_text(encoding="utf-8")
        cls.script_source = (ROOT / "static" / "teacher-media-script-1014.js").read_text(encoding="utf-8")

    def test_asset_is_loaded_on_system_surface(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertIn("/teacher-media-audio-1014.js", body)
        self.assertLess(body.index("/teacher-media-script-1014.js"), body.index("/teacher-media-audio-1014.js"))

    def test_only_approved_teacher_scripts_are_selectable(self):
        self.assertIn("item.status === 'approved'", self.source)
        self.assertIn("只能使用目前仍為「已核准」狀態的講稿", self.source)
        self.assertIn("/api/media-scripts?materialId=", self.source)

    def test_script_approval_immediately_syncs_narration_options(self):
        self.assertIn("syncNarrationOptions", self.script_source)
        self.assertIn("window.TeacherMediaAudio1014?.loadApprovedScripts", self.script_source)
        self.assertGreaterEqual(self.script_source.count("await syncNarrationOptions()"), 2)
        self.assertIn("scripts.length === 1", self.source)

    def test_narration_uses_async_worker_contract(self):
        self.assertIn("/api/media-audio/generate", self.source)
        self.assertIn("/api/media-audio/jobs/", self.source)
        self.assertIn("AI 語音處理中", self.source)
        self.assertIn("已直接保存至 R2 並加入教材", self.source)

    def test_completed_audio_refreshes_course_material_views(self):
        self.assertIn("window.invalidateAdminMaterialsCache?.()", self.source)
        self.assertIn("window.renderAdminCourseMaterialHub?.(true)", self.source)
        self.assertIn("window.renderSlidesGrid?.()", self.source)
        self.assertIn("教材清單已同步更新", self.source)

    def test_service_status_and_ai_disclosure_are_visible(self):
        self.assertIn("/api/media-audio/status", self.source)
        self.assertIn("teacher-audio-provider-1014", self.source)
        self.assertIn("teacher-audio-disclosure-1014", self.source)
        self.assertIn("本音訊為 AI 合成語音", self.source)

    def test_ui_does_not_reimplement_authorization(self):
        self.assertIn("has('material.manage')", self.source)
        self.assertNotIn("X-Admin-Key", self.source)
        self.assertNotIn("getAdminKey", self.source)
        self.assertNotIn("professionalTitle", self.source)
        self.assertNotIn("responsibilityTags", self.source)


if __name__ == "__main__":
    unittest.main()
