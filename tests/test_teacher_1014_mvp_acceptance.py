from pathlib import Path
import unittest

from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class Teacher1014MvpAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = (ROOT / "static" / "teacher-workspace-1014.js").read_text(encoding="utf-8")
        cls.script_studio = (ROOT / "static" / "teacher-media-script-1014.js").read_text(encoding="utf-8")
        cls.audio_studio = (ROOT / "static" / "teacher-media-audio-1014.js").read_text(encoding="utf-8")
        cls.recorder = (ROOT / "static" / "teacher-media-recorder-1014.js").read_text(encoding="utf-8")
        cls.paper_export = (ROOT / "static" / "admin-results-export.js").read_text(encoding="utf-8")
        cls.system_focus = (ROOT / "static" / "system-admin-focus-1014.js").read_text(encoding="utf-8")
        cls.system_shell = (ROOT / "static" / "workspace-shell-70.js").read_text(encoding="utf-8")

    def test_acceptance_persona_switch_keeps_one_account_with_separate_surfaces(self):
        for label in ("📚 我的學習", "👨‍🏫 教師工作區", "⚙ 系統管理"):
            self.assertIn(label, self.workspace)
        self.assertIn("const canLearn = roles.has('student') ||", self.workspace)
        self.assertIn("has('course.view') && has('material.read') && has('exam.take') && has('progress.self.read')", self.workspace)
        self.assertIn("const canTeach = hasTeachingRole", self.workspace)
        self.assertIn("const canSystem = roles.has('system_admin')", self.workspace)
        self.assertNotIn("X-Admin-Key", self.workspace)

    def test_acceptance_teacher_navigation_has_two_jobs_and_guided_contextual_tools(self):
        for label in ("📚 教材與課程", "📝 評量與追蹤"):
            self.assertIn(label, self.workspace)
        self.assertNotIn("makeNavButton('teacher-nav-announcements-1014'", self.workspace)
        self.assertNotIn("makeNavButton('teacher-nav-documents-1014'", self.workspace)
        self.assertIn("teacher-inline-support-1014", self.workspace)
        self.assertIn("teacher-guide-open-1014", self.workspace)
        self.assertIn("teacher-account-open-1014", self.workspace)
        self.assertNotIn("utilityButton('teacher-announcements-open-1014'", self.workspace)
        self.assertNotIn("utilityButton('teacher-documents-open-1014'", self.workspace)
        for guided_job in ("課程設定", "教材＋AI", "評量／考卷", "確認發布"):
            self.assertIn(guided_job, self.workspace)
        self.assertIn("指定完成／自由選讀", self.workspace)
        self.assertIn("teacher-guide-start-course-1014", self.workspace)
        self.assertNotIn("data-teacher-guide-action", self.workspace)
        for followup in ("學員追蹤", "臨床技能評核", "能力追蹤", "教學分析"):
            self.assertIn(followup, self.workspace)
        self.assertIn("navHost.replaceChildren(navGroup('教師工作台', buttons))", self.workspace)

    def test_acceptance_system_admin_does_not_duplicate_daily_teaching_navigation(self):
        for label in ("人員與權限", "系統健康與維運", "安全與稽核"):
            self.assertIn(label, self.system_shell)
        self.assertNotIn("navGroup('教學管理'", self.system_shell)
        self.assertNotIn("navHost.replaceChildren", self.system_focus)
        self.assertNotIn("正式文件治理", self.system_focus)
        self.assertIn("紙本輸出與範本維護已移至「教師工作區」", self.system_focus)
        for nav_id in ("admin-nav-course-materials", "admin-nav-assessment", "admin-nav-results", "admin-nav-word"):
            self.assertIn(nav_id, self.system_focus)

    def test_acceptance_media_chain_requires_teacher_approved_script(self):
        self.assertIn("AI 草稿 → 教師核准", self.script_studio)
        self.assertIn("status:statusValue", self.script_studio)
        self.assertIn("updateSavedScript('approved')", self.script_studio)
        self.assertIn("item.status === 'approved'", self.audio_studio)
        self.assertIn("只能使用目前仍為「已核准」狀態的講稿", self.audio_studio)
        self.assertIn("/api/media-audio/generate", self.audio_studio)

    def test_acceptance_browser_recording_uses_existing_direct_upload_lane(self):
        self.assertIn("No media bytes are POSTed through the Render Web process", self.recorder)
        self.assertIn("window.MaterialUploadClient.enqueue", self.recorder)
        self.assertIn("Browser → R2", self.recorder)
        self.assertIn("navigator.mediaDevices.getDisplayMedia", self.recorder)
        self.assertIn("navigator.mediaDevices.getUserMedia", self.recorder)
        self.assertNotIn("X-Admin-Key", self.recorder)

    def test_acceptance_generated_media_returns_to_course_materials(self):
        self.assertIn("回教材與課程查看", self.audio_studio)
        self.assertIn("window.invalidateAdminMaterialsCache?.()", self.audio_studio)
        self.assertIn("window.renderAdminCourseMaterialHub?.(true)", self.audio_studio)
        self.assertIn("已直接保存至 R2 並加入教材", self.audio_studio)

    def test_acceptance_paper_word_export_contains_retention_trace_fields(self):
        for field in (
            "documentReference",
            "documentVersion",
            "assessmentDate",
            "exportedAt",
            "exportedBy",
            "paperStatus",
            "examineeSignature",
            "evaluatorSignature",
            "reviewSignature",
            "signatureDate",
            "archiveNumber",
            "archiveNote",
        ):
            self.assertIn(field, self.paper_export)
        self.assertIn("exportRecordToWord", self.paper_export)
        self.assertIn("/api/doc-templates/${groupKey}/download", self.paper_export)

    def test_acceptance_required_teacher_assets_are_loaded(self):
        body = ASSET_MANIFEST["system"]["body"]
        required = (
            "/teacher-workspace-1014.js",
            "/teacher-media-script-1014.js",
            "/teacher-media-audio-1014.js",
            "/material-upload-client.js",
            "/teacher-media-recorder-1014.js",
            "/admin-results-export.js",
        )
        for asset in required:
            self.assertIn(asset, body)
        self.assertLess(body.index("/teacher-media-script-1014.js"), body.index("/teacher-media-audio-1014.js"))
        self.assertLess(body.index("/material-upload-client.js"), body.index("/teacher-media-recorder-1014.js"))


if __name__ == "__main__":
    unittest.main()
