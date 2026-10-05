from pathlib import Path
import unittest

from teacher_app.config import database_identity


ROOT = Path(__file__).resolve().parents[1]


class AIMediaConvergence20261005Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker = ROOT.joinpath("ai_question_worker.py").read_text(encoding="utf-8")
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

    def test_ai_worker_cannot_remain_falsely_healthy_without_heartbeat(self):
        for marker in (
            "AI_WORKER_HEARTBEAT_FAILURE_LIMIT",
            "AI_WORKER_HEARTBEAT_STARTUP_ATTEMPTS",
            "raise_if_unhealthy",
            "databaseIdentity",
            "databaseReady",
            "heartbeatContract",
            "_post_web_heartbeat",
            "/api/material-worker/heartbeat",
        ):
            self.assertIn(marker, self.worker)
        self.assertIn("worker_database_unavailable", self.routes)
        self.assertIn("worker_database_mismatch", self.routes)
        self.assertIn("databaseIdentityMatch", self.routes)
        self.assertIn("databaseIdentityMatch", self.operations)
        self.assertIn("DB 與 Render 不一致", self.worker_ui)

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
        self.assertIn("講稿、配音、字幕、影片皆可用", self.studio)


if __name__ == "__main__":
    unittest.main()
