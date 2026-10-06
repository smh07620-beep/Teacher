from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ASSETS = (ROOT / "teacher_app" / "frontend" / "assets.py").read_text(encoding="utf-8")
UI = (ROOT / "static" / "teacher-interface-convergence-1014.js").read_text(encoding="utf-8")
VOICE_CATALOG = (ROOT / "static" / "teacher-voice-catalog-1026.js").read_text(encoding="utf-8")
VOICE_RUNTIME = (ROOT / "teacher_app" / "materials" / "media_audio_runtime.py").read_text(encoding="utf-8")
VOICE_CONSUMERS = [
    (ROOT / "static" / name).read_text(encoding="utf-8")
    for name in (
        "teacher-media-audio-1014.js",
        "teacher-ai-video-1015.js",
        "teacher-interface-convergence-1014.js",
        "teacher-assignment-experience-1014.js",
    )
]


class TeacherInterfaceConvergence1014Tests(unittest.TestCase):
    def test_asset_is_loaded_before_final_teacher_persona_guard(self):
        self.assertIn('"/teacher-interface-convergence-1014.js"', ASSETS)
        self.assertLess(
            ASSETS.index('"/teacher-interface-convergence-1014.js"'),
            ASSETS.index('"/teacher-persona-isolation-1014.js"'),
        )

    def test_voice_labels_have_one_backend_source_and_one_frontend_catalog(self):
        self.assertIn('"/teacher-voice-catalog-1026.js"', ASSETS)
        self.assertLess(
            ASSETS.index('"/teacher-voice-catalog-1026.js"'),
            ASSETS.index('"/teacher-media-audio-1014.js"'),
        )
        self.assertIn("voiceOptions", VOICE_CATALOG)
        self.assertIn("TeacherVoiceCatalog1026", VOICE_CATALOG)
        self.assertIn('"zf_001": "中文女聲 A"', VOICE_RUNTIME)
        self.assertIn('"zm_012": "中文男聲 D"', VOICE_RUNTIME)
        for source in VOICE_CONSUMERS:
            self.assertIn("TeacherVoiceCatalog1026", source)
            self.assertNotIn("中文女聲 A", source)
            self.assertNotIn("中文男聲 D", source)
            for legacy_id in (
                "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
                "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
            ):
                self.assertNotIn(legacy_id, source)

    def test_media_is_nested_under_course_workspace(self):
        self.assertIn("document.getElementById('teacher-nav-media-1014')?.remove()", UI)
        self.assertIn("需要時進製作室做 PowerPoint／講稿／影音", UI)
        self.assertIn("AI 製作是選配", UI)
        self.assertIn("建立或更新課程並發布／指派", UI)
        self.assertIn("🧰 開啟教材媒體製作室", UI)
        self.assertIn("TeacherWorkspace1014?.openMedia", UI)
        self.assertNotIn("TeacherWorkspace1014?.openPresentation", UI)

    def test_course_card_has_single_management_entry(self):
        self.assertIn("data-teacher-manage-course-1014", UI)
        self.assertIn("管理課程", UI)
        self.assertIn("內容編排", UI)
        self.assertIn("學習指派", UI)
        self.assertIn("刪除課程", UI)
        self.assertIn("button.classList.add('hidden')", UI)
        self.assertIn("setAttribute('data-teacher-manage-course-1014', '1')", UI)

    def test_course_card_reconciliation_is_not_deferred_to_animation_frame(self):
        observer = UI[UI.index("state.courseObserver = new MutationObserver"):UI.index("    // MutationObserver callbacks run")]
        self.assertIn("convergeCourseSurface();", observer)
        self.assertNotIn("requestAnimationFrame(()", observer)

    def test_course_renderer_announces_completed_card_replacement(self):
        course_hub = (ROOT / "static" / "admin-course-material.js").read_text(encoding="utf-8")
        self.assertIn("teacher-course-surface-rendered-1014", course_hub)
        self.assertIn("teacher-course-surface-rendered-1014", UI)


if __name__ == "__main__":
    unittest.main()
