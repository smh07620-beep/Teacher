from pathlib import Path
import unittest

from teacher_app.config import database_identity


ROOT = Path(__file__).resolve().parents[1]


class AIMediaConvergence20261005Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker = ROOT.joinpath("ai_question_worker.py").read_text(encoding="utf-8")
        cls.remote = ROOT.joinpath("teacher_app", "worker", "ai_remote.py").read_text(encoding="utf-8")
        cls.worker_routes = ROOT.joinpath("teacher_app", "worker", "routes.py").read_text(encoding="utf-8")
        cls.routes = ROOT.joinpath("teacher_app", "materials", "media_audio_routes.py").read_text(encoding="utf-8")
        cls.operations = ROOT.joinpath("teacher_app", "worker", "operations.py").read_text(encoding="utf-8")
        cls.worker_ui = ROOT.joinpath("static", "worker-status-70.js").read_text(encoding="utf-8")
        cls.studio = ROOT.joinpath("static", "teacher-ai-media-studio-1018.js").read_text(encoding="utf-8")
        cls.controls = ROOT.joinpath("static", "teacher-ai-media-controls-1023.js").read_text(encoding="utf-8")
        cls.script = ROOT.joinpath("static", "teacher-media-script-1014.js").read_text(encoding="utf-8")
        cls.audio = ROOT.joinpath("static", "teacher-media-audio-1014.js").read_text(encoding="utf-8")
        cls.video = ROOT.joinpath("static", "teacher-ai-video-1015.js").read_text(encoding="utf-8")
        cls.convergence = ROOT.joinpath("static", "teacher-ai-material-convergence-1014.js").read_text(encoding="utf-8")

    def test_supabase_direct_and_pooler_urls_have_same_non_secret_identity(self):
        direct = database_identity({
            "DATABASE_URL": "postgresql://postgres:secret@db.abc123.supabase.co:5432/postgres"
        })
        pooler = database_identity({
            "DATABASE_URL": "postgresql://postgres.abc123:secret@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
        })
        other = database_identity({
            "DATABASE_URL": "postgresql://postgres.other999:secret@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
        })
        self.assertEqual(direct, pooler)
        self.assertNotEqual(direct, other)
        self.assertEqual(len(direct), 16)
        self.assertNotIn("secret", direct)

    def test_ai_worker_uses_https_control_plane_without_hospital_postgres(self):
        for marker in (
            "ai_remote.transport_mode()",
            "ai_remote.TRANSPORT_HTTPS",
            "AIWorkerApi",
            "install_remote_repository_proxies",
            "control_transport=",
            "heartbeatContract",
            "heartbeatTransport",
        ):
            self.assertIn(marker, self.worker)
        for marker in (
            "/api/ai-worker/heartbeat",
            "/api/ai-worker/rpc",
            "AI_WORKER_TOKEN",
            "AI_WORKER_HTTP_RATE_LIMIT_PER_MINUTE",
        ):
            self.assertIn(marker, self.worker_routes)
        for marker in (
            "TRANSPORT_HTTPS",
            "queue.touch",
            "r2.record_object",
            "presentation.create_presentation",
            "video.create_video",
            "subtitle.create_subtitle",
        ):
            self.assertIn(marker, self.remote)
        self.assertIn("controlPlaneReady", self.routes)
        self.assertIn("HTTPS 443 control plane", self.routes)
        self.assertIn("controlPlaneReady", self.operations)
        self.assertIn("HTTPS 443 控制通道", self.worker_ui)
        self.assertNotIn('"/api/material-worker/heartbeat"', self.worker)


    def test_script_and_narration_are_one_guided_flow(self):
        self.assertIn("🎙️ 講稿與配音", self.studio)
        self.assertIn("teacher-media-narration-flow-1028", self.studio)
        self.assertNotIn("makeDetails('講稿草稿與版本'", self.studio)
        self.assertIn("teacher-media-script-approved-1027", self.script)
        self.assertIn("teacher-media-script-approved-1027", self.audio)
        self.assertIn("preferredScriptId", self.audio)
        self.assertIn("legacy.closest('#teacher-media-panel-narration-1018')", self.convergence)

    def test_video_can_start_from_private_non_ppt_sources(self):
        for marker in (
            "來源內容 + 旁白 → 教學影片",
            "teacher-ai-video-source-author-1028",
            "PDF／Word／圖片／文字",
            "不必先發布成正式教材",
        ):
            self.assertIn(marker, self.video)
        self.assertIn("openVideoSourceWorkspace", self.controls)
        self.assertIn("purpose:'video'", self.controls)
        self.assertIn("VIDEO SOURCE AUTHORING", self.controls)
        self.assertIn("私人製作來源", self.controls)
        self.assertIn("PowerPoint、講稿／配音、老師錄影與 AI 教學影片共用同一個製作室", self.studio)
        self.assertIn("📹 老師自己錄影", self.studio)
        self.assertIn("teacher-media-video-captions-1018", self.studio)
        self.assertNotIn("teacher-media-tab-subtitle-1018", self.studio)


if __name__ == "__main__":
    unittest.main()
