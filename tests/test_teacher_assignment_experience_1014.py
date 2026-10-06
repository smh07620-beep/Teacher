from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ASSETS = (ROOT / "teacher_app" / "frontend" / "assets.py").read_text(encoding="utf-8")
UI = (ROOT / "static" / "teacher-assignment-experience-1014.js").read_text(encoding="utf-8")
ASSIGNMENT_ROUTES = (ROOT / "teacher_app" / "learning" / "assignment_routes.py").read_text(encoding="utf-8")
ASSIGNMENT_SERVICE = (ROOT / "teacher_app" / "learning" / "assignment_service.py").read_text(encoding="utf-8")
AUDIO_ROUTES = (ROOT / "teacher_app" / "materials" / "media_audio_routes.py").read_text(encoding="utf-8")
AUDIO_JOBS = (ROOT / "teacher_app" / "materials" / "media_audio_jobs.py").read_text(encoding="utf-8")
AUDIO_RUNTIME = (ROOT / "teacher_app" / "materials" / "media_audio_runtime.py").read_text(encoding="utf-8")
AUDIO_REPO = (ROOT / "teacher_app" / "materials" / "media_audio_repository.py").read_text(encoding="utf-8")


class TeacherAssignmentExperience1014Tests(unittest.TestCase):
    def test_experience_layer_loads_after_interface_convergence(self):
        self.assertIn('"/teacher-assignment-experience-1014.js"', ASSETS)
        self.assertLess(
            ASSETS.index('"/teacher-interface-convergence-1014.js"'),
            ASSETS.index('"/teacher-assignment-experience-1014.js"'),
        )

    def test_assignment_dialog_uses_scoped_group_and_person_choices(self):
        self.assertIn('/api/learning-assignments/audience-options', UI)
        self.assertIn('learning-assignment-person-search-1014', UI)
        self.assertIn("指定人員", UI)
        self.assertIn("搜尋姓名、工號或帳號", UI)
        self.assertIn('account.get("preferredGroup")', ASSIGNMENT_SERVICE)
        self.assertIn('allowedAssigneeTypes', ASSIGNMENT_SERVICE)
        self.assertIn('["group", "user"]', ASSIGNMENT_SERVICE)
        self.assertIn('ASSIGNEE_SCOPE_MISMATCH', ASSIGNMENT_SERVICE)
        self.assertIn('指定人員目前不屬於此課程的訓練區／組別', ASSIGNMENT_SERVICE)
        self.assertIn('@app.get("/api/learning-assignments/audience-options")', ASSIGNMENT_ROUTES)

    def test_batch_course_assignment_is_available_and_idempotent_friendly(self):
        self.assertIn('teacher-batch-assignment-dialog-1014', UI)
        self.assertIn('批次管理課程', UI)
        self.assertIn('全選／取消全選', UI)
        self.assertIn('ASSIGNMENT_EXISTS', UI)
        self.assertIn("body:JSON.stringify({courseId:selected[index]", UI)

    def test_kokoro_voice_preview_uses_worker_and_cached_r2_audio(self):
        self.assertIn('/api/media-audio/preview', UI)
        self.assertIn('▶ 試聽聲音', UI)
        self.assertIn('previewUrl', UI)
        self.assertIn('@app.post("/api/media-audio/preview")', AUDIO_ROUTES)
        self.assertIn('enqueue_preview', AUDIO_JOBS)
        self.assertIn('generate_voice_preview', AUDIO_RUNTIME)
        self.assertIn('system/voice-previews/kokoro/', AUDIO_RUNTIME)
        self.assertIn('VOICE_PREVIEW_TEXT', AUDIO_RUNTIME)
        self.assertIn('setTimeout(resolve, 700)', UI)
        preview_body = AUDIO_RUNTIME.split('def generate_voice_preview', 1)[1].split('def preview_url', 1)[0]
        self.assertNotIn('_insert_material_if_missing', preview_body)
        self.assertIn('短版試聽已可播放', AUDIO_REPO)
        self.assertIn('WAV 已存入教材庫', AUDIO_REPO)

    def test_explanations_are_collapsed_on_demand(self):
        self.assertIn('data-paper-guidance-toggle', UI)
        self.assertIn('展開檢核', UI)
        self.assertIn('列印／匯出前確認文件版本、簽核、日期與留存要求', UI)
        self.assertNotIn('？ 紙本留存說明與檢核', UI)
        self.assertIn('？ 工作區說明', UI)
        self.assertIn('collapsePaperGuidance', UI)
        self.assertIn('collapseWorkspaceSummary', UI)


if __name__ == "__main__":
    unittest.main()
