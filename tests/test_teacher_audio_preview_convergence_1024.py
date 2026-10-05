from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUDIO = (ROOT / "static" / "teacher-media-audio-1014.js").read_text(encoding="utf-8")
ASSIGNMENT = (ROOT / "static" / "teacher-assignment-experience-1014.js").read_text(encoding="utf-8")
ROUTES = (ROOT / "teacher_app" / "materials" / "media_audio_routes.py").read_text(encoding="utf-8")
REPOSITORY = (ROOT / "teacher_app" / "materials" / "media_audio_repository.py").read_text(encoding="utf-8")


class TeacherAudioPreviewConvergence1024Tests(unittest.TestCase):
    def test_narration_preview_has_one_control_owner_and_one_shared_status_region(self):
        self.assertNotIn("teacher-audio-preview-1018", AUDIO)
        self.assertIn("teacher-audio-preview-1014", ASSIGNMENT)
        self.assertIn("▶ 試聽聲音", ASSIGNMENT)
        self.assertIn("teacher-audio-status-1014", AUDIO)
        self.assertIn("teacher-audio-status-1014", ASSIGNMENT)
        self.assertIn('role="status"', AUDIO)
        self.assertIn('aria-live="polite"', AUDIO)

    def test_existing_formal_job_disables_preview_after_workspace_hydration(self):
        self.assertIn("active_formal_job_for_actor", REPOSITORY)
        self.assertIn('payload["activeJob"]', ROUTES)
        self.assertIn("teacher-media-audio-formal-busy-1014", AUDIO)
        self.assertIn("teacher-media-audio-formal-busy-1014", ASSIGNMENT)
        self.assertIn("正式 AI 語音工作正在排隊或處理中", ASSIGNMENT)

    def test_preview_progress_reports_worker_state_instead_of_only_preparing(self):
        self.assertIn("progress.detail", ASSIGNMENT)
        self.assertIn("attempt < 60", ASSIGNMENT)
        self.assertIn("fetchJsonWithTimeout", ASSIGNMENT)
        self.assertIn("請確認 Worker 在線後再試", ASSIGNMENT)
        self.assertNotIn("目前已有 AI 語音工作排隊或執行中", ASSIGNMENT)
