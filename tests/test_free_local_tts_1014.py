from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FreeLocalTTS1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = (ROOT / "teacher_app" / "materials" / "media_audio_runtime.py").read_text(encoding="utf-8")
        cls.jobs = (ROOT / "teacher_app" / "materials" / "media_audio_jobs.py").read_text(encoding="utf-8")
        cls.render = (ROOT / "render.yaml").read_text(encoding="utf-8")
        cls.env = (ROOT / ".local-worker.env.example").read_text(encoding="utf-8")
        cls.worker_requirements = (ROOT / "requirements-ai-worker.txt").read_text(encoding="utf-8")
        cls.ui = (ROOT / "static" / "teacher-media-free-tts-1014.js").read_text(encoding="utf-8")
        cls.audio_ui = (ROOT / "static" / "teacher-media-audio-1014.js").read_text(encoding="utf-8")
        cls.video_ui = (ROOT / "static" / "teacher-ai-video-1015.js").read_text(encoding="utf-8")
        cls.status_ui = (ROOT / "static" / "teacher-media-status-fix-1014.js").read_text(encoding="utf-8")
        cls.worker = (ROOT / "ai_question_worker.py").read_text(encoding="utf-8")
        cls.routes = (ROOT / "teacher_app" / "materials" / "media_audio_routes.py").read_text(encoding="utf-8")
        cls.video_routes = (ROOT / "teacher_app" / "materials" / "ai_video_routes.py").read_text(encoding="utf-8")
        cls.worker_ops = (ROOT / "teacher_app" / "worker" / "operations.py").read_text(encoding="utf-8")

    def test_narration_is_local_kokoro_only(self):
        for marker in (
            'from kokoro import KPipeline',
            'lang_code="z"',
            'hexgrad/Kokoro-82M-v1.1-zh',
            'DEFAULT_VOICE = "zf_001"',
            'ttsProvider": "kokoro-local"',
            'ContentType="audio/wav"',
        ):
            self.assertIn(marker, self.runtime)
        self.assertNotIn('api.openai.com', self.runtime)
        self.assertNotIn('OPENAI_API_KEY', self.runtime)

    def test_kokoro_pipeline_is_reused_and_preview_text_stays_short(self):
        self.assertIn("_KOKORO_PIPELINE", self.runtime)
        self.assertIn("def _kokoro_pipeline", self.runtime)
        self.assertIn("pipeline = _kokoro_pipeline(repo_id)", self.runtime)
        self.assertIn("voice = _voice(voice)", self.runtime)
        self.assertIn("voiceOptions", self.runtime)
        self.assertIn('VOICE_PREVIEW_TEXT = "您好，這是醫學檢驗教學平台的 AI 語音試聽。"', self.runtime)

    def test_render_and_local_env_do_not_require_openai(self):
        self.assertIn('AI_TTS_PROVIDER\n        value: kokoro', self.render)
        self.assertIn('FREE_ONLY_MODE\n        value: "true"', self.render)
        self.assertNotIn('OPENAI_API_KEY', self.render)
        self.assertNotIn('OPENAI_TTS_MODEL', self.render)
        self.assertNotIn('OPENAI_API_KEY', self.env)
        self.assertIn('AI_TTS_PROVIDER=kokoro', self.env)
        self.assertIn('KOKORO_VOICE=zf_001', self.env)

    def test_ai_worker_has_separate_local_tts_dependencies(self):
        for marker in ('kokoro>=', 'misaki[zh]', 'numpy>='):
            self.assertIn(marker, self.worker_requirements)
        self.assertNotIn('openai', self.worker_requirements.lower())

    def test_ui_explains_free_local_narration(self):
        self.assertIn('免費 AI 語音', self.ui)
        self.assertIn('本機 Kokoro', self.ui)
        self.assertIn('不呼叫 OpenAI TTS', self.ui)
        self.assertNotIn("fetch('/api/media-audio/status'", self.ui)
        self.assertIn("TeacherMediaAudioStatus1014", self.ui)
        self.assertIn("teacher-media-audio-status-1014", self.ui)

    def test_ai_voice_service_health_is_visible_and_backed_by_worker_heartbeat(self):
        self.assertIn('"workerKind": "ai"', self.worker)
        self.assertIn('AI_WORKER_HEARTBEAT_SECONDS', self.worker)
        self.assertIn('"misaki": misaki_ready', self.worker)
        self.assertIn('"whisper": {"available": whisper_ready}', self.worker)
        self.assertIn('readyForPreview', self.routes)
        self.assertIn('kokoroInstalled', self.routes)
        self.assertIn('teacher-audio-health-1014', self.audio_ui)
        self.assertIn('AI Worker 在線', self.audio_ui)
        self.assertIn('Kokoro 已安裝', self.audio_ui)
        self.assertIn('R2 正常', self.audio_ui)
        self.assertIn('teacher-ai-video-voice-health-1015', self.video_ui)

    def test_voice_readiness_reports_actionable_worker_diagnostics(self):
        self.assertIn("heartbeatAgeSeconds", self.routes)
        self.assertIn("diagnosticMessage", self.routes)
        self.assertIn("worker_not_seen", self.routes)
        self.assertIn("worker_code_mismatch", self.routes)
        self.assertIn("codeIdentityMatch", self.routes)
        self.assertIn("workerSha", self.worker)
        self.assertIn('"repoId":', self.worker)
        self.assertIn("kokoro_unavailable", self.routes)
        self.assertIn("readyForPreview", self.status_ui)
        self.assertIn("statusUnavailable", self.audio_ui)
        self.assertIn("AI Worker 狀態讀取失敗", self.audio_ui)
        self.assertIn("Kokoro 無法確認", self.audio_ui)
        self.assertIn("statusUnavailable", self.video_ui)
        self.assertIn("AI Worker 狀態讀取失敗", self.video_ui)
        self.assertIn("Kokoro 無法確認", self.video_ui)
        self.assertIn("AI Worker 狀態讀取失敗", self.status_ui)
        self.assertIn("Kokoro 能力未回報", self.audio_ui)
        self.assertIn("Kokoro 能力未回報", self.video_ui)

    def test_worker_readiness_accepts_compatible_ai_heartbeat_shapes(self):
        self.assertIn("_is_ai_worker_heartbeat", self.routes)
        self.assertIn('worker_id.endswith("-ai")', self.routes)
        self.assertIn('queue_names.intersection(_AI_QUEUE_NAMES)', self.routes)
        self.assertIn("_kokoro_capability", self.routes)
        self.assertIn('"kokoroInstalled"', self.routes)
        self.assertIn('"queues": queues', self.routes)
        self.assertIn("required_queue", self.routes)
        self.assertIn("workerCapabilityMissing", self.routes)

    def test_audio_and_video_generation_fail_closed_when_worker_is_not_ready(self):
        self.assertIn("_worker_ready_error", self.routes)
        self.assertIn("readiness_error = _worker_ready_error()", self.routes)
        self.assertIn("workerOffline", self.routes)
        self.assertIn("kokoroUnavailable", self.routes)
        self.assertIn('"ready": ready', self.video_routes)
        self.assertIn("worker = _ai_worker_status()", self.video_routes)
        self.assertIn('_ai_worker_online_error(worker, required_queue="ai_videos")', self.video_routes)
        self.assertIn("kokoroUnavailable", self.video_routes)
        self.assertIn("!statusInfo?.readyForPreview", self.audio_ui)
        self.assertIn("!status?.ready", self.video_ui)

    def test_ai_heartbeat_does_not_appear_as_duplicate_material_worker(self):
        self.assertIn('capabilities.get("workerKind")', self.worker_ops)
        self.assertIn('== "ai"', self.worker_ops)
        self.assertIn("def _latest_ai_heartbeat_per_machine", self.worker_ops)
        self.assertIn('"aiWorkers": ai_workers', self.worker_ops)

    def test_one_audio_status_owner_broadcasts_to_all_media_views(self):
        self.assertIn("teacher-media-audio-status-1014", self.audio_ui)
        self.assertIn("TeacherMediaAudioStatus1014", self.audio_ui)
        self.assertNotIn("fetch('/api/media-audio/status'", self.ui)
        self.assertNotIn("fetch('/api/media-audio/status'", self.status_ui)
        self.assertIn("teacher-media-audio-status-1014", self.video_ui)

    def test_enqueue_error_mentions_local_free_runtime(self):
        self.assertIn('免費本機 AI 語音尚未啟用', self.jobs)
        self.assertIn('Kokoro AI Worker', self.jobs)
        self.assertNotIn('OPENAI_API_KEY', self.jobs)


if __name__ == '__main__':
    unittest.main()
