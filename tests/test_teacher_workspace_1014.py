from pathlib import Path
import unittest

from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class TeacherWorkspace1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "teacher-workspace-1014.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "static" / "teacher-workspace-1014.css").read_text(encoding="utf-8")

    def test_asset_is_loaded_after_workspace_shell(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertIn("/teacher-workspace-1014.js", body)
        self.assertLess(body.index("/workspace-shell-70.js"), body.index("/teacher-workspace-1014.js"))
        self.assertIn("/teacher-workspace-1014.css", ASSET_MANIFEST["system"]["head"])

    def test_dual_role_persona_switch_requires_real_capabilities(self):
        self.assertIn("const canTeach = hasTeachingRole", self.source)
        self.assertIn("const canLearn = roles.has('student') ||", self.source)
        self.assertIn("has('course.view') && has('material.read') && has('exam.take') && has('progress.self.read')", self.source)
        self.assertIn("📚 我的學習", self.source)
        self.assertIn("👨‍🏫 教師工作區", self.source)
        self.assertIn("choices.length < 2", self.source)
        self.assertIn("url.searchParams.delete(key)", self.source)

    def test_mobile_persona_switch_stays_reachable_without_becoming_bottom_nav(self):
        self.assertIn("#teacher-persona-switch-1014", self.styles)
        self.assertIn("display: flex", self.styles)
        self.assertIn("overflow-x: auto", self.styles)
        self.assertIn("white-space: nowrap", self.styles)
        self.assertIn("@media (max-width: 820px)", self.styles)
        self.assertNotIn("position: fixed", self.styles)
        self.assertNotIn("bottom:", self.styles)

    def test_teacher_navigation_is_two_primary_jobs_with_header_utilities(self):
        for label in (
            "📚 教材與課程",
            "📝 評量與追蹤",
        ):
            self.assertIn(label, self.source)
        self.assertNotIn("makeNavButton('teacher-nav-announcements-1014'", self.source)
        self.assertNotIn("makeNavButton('teacher-nav-documents-1014'", self.source)
        self.assertIn("teacher-inline-support-1014", self.source)
        self.assertIn("teacher-guide-open-1014", self.source)
        self.assertNotIn("teacher-account-open-1014", self.source)  # account settings live in the outer header
        self.assertNotIn("utilityButton('teacher-announcements-open-1014'", self.source)
        self.assertNotIn("utilityButton('teacher-documents-open-1014'", self.source)
        self.assertIn("AI 製作從課程的教材流程內進入", self.source)
        self.assertIn("navHost.replaceChildren(navGroup('教師工作台', buttons))", self.source)

    def test_first_use_guide_explains_the_complete_teacher_job(self):
        for marker in (
            "teacher-usage-guide-1014",
            "建立一門課，照這四步完成",
            "課程設定",
            "教材＋AI",
            "評量／考卷",
            "確認發布",
            "指定完成／自由選讀",
            "發布後：",
            "學員追蹤",
            "臨床技能評核",
            "能力追蹤",
            "教學分析",
            "openReview",
            "openLearnerTracking",
        ):
            self.assertIn(marker, self.source)
        self.assertNotIn("data-teacher-guide-action", self.source)

    def test_media_workspace_reuses_course_material_scope(self):
        self.assertIn("await window.AppWorkspaceRoutes.show('course-materials', true)", self.source)
        self.assertIn("教材 → 講稿 → 語音／影片 → 發布", self.source)
        self.assertIn("正式發布仍沿用原教材權限", self.source)
        self.assertNotIn("/api/media-generation", self.source)
        self.assertNotIn("X-Admin-Key", self.source)

    def test_powerpoint_opens_stable_unified_studio_tab(self):
        self.assertIn("async function openPresentation()", self.source)
        self.assertIn("await openMedia()", self.source)
        self.assertIn("TeacherAIMediaStudio1018?.showMode?.('presentation')", self.source)
        self.assertIn("teacher-media-panel-presentation-1018", self.source)
        self.assertNotIn("id=\"teacher-media-open-presentation-1014\"", self.source)

    def test_paper_documents_reuse_existing_teacher_export_flow(self):
        self.assertIn("await window.AppWorkspaceRoutes.show('teacher', true)", self.source)
        self.assertIn("await window.switchTeacherMode?.('documents')", self.source)
        self.assertNotIn("template.manage", self.source)

    def test_manual_review_stays_under_assessment_not_new_top_level_nav(self):
        self.assertIn("歷史紀錄", self.source)
        self.assertIn("teacher-assessment-pending-badge-1030", self.source)
        self.assertIn('data-assessment-tab-1030="history"', self.source)
        self.assertIn("await window.AppWorkspaceRoutes.show('results', true)", self.source)
        self.assertNotIn("待批改／教師評核", self.source)

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
