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

    def test_narration_is_local_kokoro_only(self):
        for marker in (
            'from kokoro import KPipeline',
            'lang_code="z"',
            'hexgrad/Kokoro-82M-v1.1-zh',
            'zf_xiaoxiao',
            'ttsProvider": "kokoro-local"',
            'ContentType="audio/wav"',
        ):
            self.assertIn(marker, self.runtime)
        self.assertNotIn('api.openai.com', self.runtime)
        self.assertNotIn('OPENAI_API_KEY', self.runtime)

    def test_render_and_local_env_do_not_require_openai(self):
        self.assertIn('AI_TTS_PROVIDER\n        value: kokoro', self.render)
        self.assertIn('FREE_ONLY_MODE\n        value: "true"', self.render)
        self.assertNotIn('OPENAI_API_KEY', self.render)
        self.assertNotIn('OPENAI_TTS_MODEL', self.render)
        self.assertNotIn('OPENAI_API_KEY', self.env)
        self.assertIn('AI_TTS_PROVIDER=kokoro', self.env)
        self.assertIn('KOKORO_VOICE=zf_xiaoxiao', self.env)

    def test_ai_worker_has_separate_local_tts_dependencies(self):
        for marker in ('kokoro>=', 'misaki[zh]', 'numpy>='):
            self.assertIn(marker, self.worker_requirements)
        self.assertNotIn('openai', self.worker_requirements.lower())

    def test_ui_explains_free_local_narration(self):
        self.assertIn('免費 AI 語音', self.ui)
        self.assertIn('本機 Kokoro', self.ui)
        self.assertIn('不呼叫 OpenAI TTS', self.ui)
        self.assertIn('/api/media-audio/status', self.ui)

    def test_enqueue_error_mentions_local_free_runtime(self):
        self.assertIn('免費本機 AI 語音尚未啟用', self.jobs)
        self.assertIn('Kokoro AI Worker', self.jobs)
        self.assertNotIn('OPENAI_API_KEY', self.jobs)


if __name__ == '__main__':
    unittest.main()
