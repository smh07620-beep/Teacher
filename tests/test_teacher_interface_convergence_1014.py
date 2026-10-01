from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ASSETS = (ROOT / "teacher_app" / "frontend" / "assets.py").read_text(encoding="utf-8")
UI = (ROOT / "static" / "teacher-interface-convergence-1014.js").read_text(encoding="utf-8")


class TeacherInterfaceConvergence1014Tests(unittest.TestCase):
    def test_asset_is_loaded_before_final_teacher_persona_guard(self):
        self.assertIn('"/teacher-interface-convergence-1014.js"', ASSETS)
        self.assertLess(
            ASSETS.index('"/teacher-interface-convergence-1014.js"'),
            ASSETS.index('"/teacher-persona-isolation-1014.js"'),
        )

    def test_kokoro_ids_are_internal_values_but_not_teacher_labels(self):
        for voice_id in (
            "zf_xiaobei",
            "zf_xiaoni",
            "zf_xiaoxiao",
            "zf_xiaoyi",
            "zm_yunjian",
            "zm_yunxi",
            "zm_yunxia",
            "zm_yunyang",
        ):
            self.assertIn(voice_id, UI)
        self.assertIn("option.value", UI)
        self.assertIn("option.textContent = label", UI)
        self.assertIn("中文女聲 A", UI)
        self.assertIn("中文男聲 D", UI)

    def test_media_is_nested_under_course_workspace(self):
        self.assertIn("document.getElementById('teacher-nav-media-1014')?.remove()", UI)
        self.assertIn("製作語音／錄影", UI)
        self.assertIn("TeacherWorkspace1014?.openMedia", UI)

    def test_course_card_has_single_management_entry(self):
        self.assertIn("data-teacher-manage-course-1014", UI)
        self.assertIn("管理課程", UI)
        self.assertIn("內容編排", UI)
        self.assertIn("學習指派", UI)
        self.assertIn("刪除課程", UI)
        self.assertIn("button.classList.add('hidden')", UI)

    def test_course_card_reconciliation_is_not_deferred_to_animation_frame(self):
        observer = UI[UI.index("state.courseObserver = new MutationObserver"):UI.index("    // MutationObserver callbacks run")]
        self.assertIn("convergeCourseSurface();", observer)
        self.assertNotIn("requestAnimationFrame(()", observer)


if __name__ == "__main__":
    unittest.main()
