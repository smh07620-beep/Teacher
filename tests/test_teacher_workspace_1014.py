from pathlib import Path
import unittest

from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class TeacherWorkspace1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "teacher-workspace-1014.js").read_text(encoding="utf-8")

    def test_asset_is_loaded_after_workspace_shell(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertIn("/teacher-workspace-1014.js", body)
        self.assertLess(body.index("/workspace-shell-70.js"), body.index("/teacher-workspace-1014.js"))

    def test_dual_role_persona_switch_requires_real_capabilities(self):
        self.assertIn("const canTeach = hasTeachingRole", self.source)
        self.assertIn("const canLearn = has('course.view')", self.source)
        self.assertIn("📚 我的學習", self.source)
        self.assertIn("👨‍🏫 教師工作區", self.source)
        self.assertIn("choices.length < 2", self.source)
        self.assertIn("url.searchParams.delete(key)", self.source)

    def test_teacher_navigation_is_focused_on_first_cut(self):
        for label in (
            "📚 教材與課程",
            "🎙️ 媒體製作",
            "📝 評量與出題",
            "📄 紙本文件與匯出",
        ):
            self.assertIn(label, self.source)
        self.assertIn("navHost.replaceChildren(navGroup('教師工作台', buttons))", self.source)

    def test_media_workspace_reuses_course_material_scope(self):
        self.assertIn("await window.switchAdminWorkspace?.('course-materials', true)", self.source)
        self.assertIn("教材 → 講稿 → 語音／影片 → 發布", self.source)
        self.assertIn("正式發布仍沿用原教材權限", self.source)
        self.assertNotIn("/api/media-generation", self.source)
        self.assertNotIn("X-Admin-Key", self.source)

    def test_paper_documents_reuse_existing_teacher_export_flow(self):
        self.assertIn("await window.switchAdminWorkspace?.('teacher', true)", self.source)
        self.assertIn("await window.switchTeacherMode?.('documents')", self.source)
        self.assertNotIn("template.manage", self.source)

    def test_manual_review_stays_under_assessment_not_new_top_level_nav(self):
        self.assertIn("待批改／教師評核", self.source)
        self.assertIn("進入閱卷與評核", self.source)
        self.assertIn("await window.switchTeacherMode?.('scoring')", self.source)

    def test_module_does_not_create_authorization_policy(self):
        for forbidden in (
            "professionalTitle",
            "responsibilityTags",
            "ROLE_PERMISSIONS",
            "require_role",
            "require_permission",
        ):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
