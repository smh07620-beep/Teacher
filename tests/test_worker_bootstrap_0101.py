from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WorkerBootstrap0101Tests(unittest.TestCase):
    def setUp(self):
        self.script = (ROOT / "setup_teacher_worker.ps1").read_text(encoding="utf-8")
        self.env_example = (ROOT / ".local-worker.env.example").read_text(encoding="utf-8")
        self.docs = (ROOT / "docs" / "WORKER_BOOTSTRAP.md").read_text(encoding="utf-8")

    def test_reuses_canonical_worker_architecture(self):
        for marker in (
            "update_material_worker.ps1",
            "install_teacher_workers.ps1",
            "requirements-ai-worker.txt",
            "Teacher Material Worker",
            "Teacher AI Worker",
            ".local-worker.env",
        ):
            self.assertIn(marker, self.script)

    def test_bootstrap_never_bypasses_safe_release_update(self):
        lowered = self.script.lower()
        self.assertNotIn("git pull", lowered)
        self.assertNotIn("git reset", lowered)
        self.assertNotIn("git clean", lowered)
        self.assertNotIn("git stash", lowered)
        self.assertIn("approved-release updater", lowered)
        self.assertIn("working tree is dirty", lowered)

    def test_worker_local_ai_prerequisites_are_covered(self):
        for marker in (
            "pptx",
            "kokoro",
            "faster_whisper",
            "ffmpeg.exe",
            "Gyan.FFmpeg",
            "ollama.exe",
            "Ollama.Ollama",
            "ollama.Source list",
            "OLLAMA_MODEL",
            "SkipDownloads",
            "InstallOptionalTools",
        ):
            self.assertIn(marker, self.script)

    def test_secret_values_are_not_logged(self):
        for secret_name in (
            "MATERIAL_WORKER_TOKEN",
            "DATABASE_URL",
            "GROQ_API_KEY",
            "GEMINI_API_KEY",
            "R2_SECRET_ACCESS_KEY",
            "MEGA_PASSWORD",
            "GDRIVE_CLIENT_SECRET",
            "GDRIVE_REFRESH_TOKEN",
        ):
            self.assertNotIn(f"Write-Host ${secret_name}", self.script)
            self.assertNotIn(f"Write-Output ${secret_name}", self.script)
        for forbidden in ("gsk_", "postgresql://postgres.", "GOCSPX-", "REPLACE_WITH_REAL_SECRET"):
            self.assertNotIn(forbidden, self.script)

    def test_stable_worker_id_and_durable_storage_are_checked(self):
        self.assertIn("MATERIAL_WORKER_ID=lab-worker-01", self.env_example)
        self.assertIn('Test-ConfiguredValue "MATERIAL_WORKER_ID"', self.script)
        for marker in (
            "R2_ACCOUNT_ID",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET_NAME",
            "GDRIVE_REFRESH_TOKEN",
            "MEGA_EMAIL",
            "AI_VIDEO_STORAGE_BACKEND",
            "AI_PRESENTATION_STORAGE_BACKEND",
        ):
            self.assertIn(marker, self.script)

    def test_task_install_is_noninteractive_only_with_service_account(self):
        self.assertIn("Non-interactive task installation requires -ServiceAccount", self.script)
        self.assertIn("-InstallTasks requires an elevated PowerShell session", self.script)
        self.assertIn("-RestartTasks requires an elevated PowerShell session", self.script)

    def test_phase2_readiness_keeps_existing_pipeline(self):
        for marker in (
            "AI Video Phase 2 authoring",
            "editable narration per slide",
            "parentRevisionId",
            "videoFamilyId",
            "clinical-teacher/group-leader approval",
            "reuse `ai_video_*`",
        ):
            self.assertIn(marker, self.docs)


if __name__ == "__main__":
    unittest.main()
