import os
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.worker import ai_remote


ROOT = Path(__file__).resolve().parents[1]


class AIWorkerHttpsControlPlane20261005Tests(unittest.TestCase):
    def test_auto_prefers_https_even_when_legacy_database_url_exists(self):
        env = {
            "AI_WORKER_TRANSPORT": "auto",
            "TEACHER_BASE_URL": "https://teacher.example.com",
            "MATERIAL_WORKER_TOKEN": "worker-secret",
            "AI_WORKER_TOKEN": "",
            "DATABASE_URL": "postgresql://blocked.example.invalid/postgres",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(ai_remote.transport_mode(), ai_remote.TRANSPORT_HTTPS)

    def test_auto_never_silently_falls_back_to_blocked_postgresql(self):
        env = {
            "AI_WORKER_TRANSPORT": "auto",
            "DATABASE_URL": "postgresql://blocked.example.invalid/postgres",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "HTTPS 443"):
                ai_remote.transport_mode()

    def test_explicit_database_transport_remains_legacy_fallback(self):
        with patch.dict(os.environ, {"AI_WORKER_TRANSPORT": "database"}, clear=True):
            self.assertEqual(ai_remote.transport_mode(), ai_remote.TRANSPORT_DATABASE)

    def test_invalid_transport_fails_closed(self):
        with patch.dict(os.environ, {"AI_WORKER_TRANSPORT": "ftp"}, clear=True):
            with self.assertRaises(RuntimeError):
                ai_remote.transport_mode()

    def test_rpc_call_id_replay_executes_mutation_once(self):
        call_id = "test-replay-" + os.urandom(6).hex()
        calls = []

        def fake_execute(op, args, kwargs):
            calls.append((op, args, kwargs))
            return {"ok": True, "value": 7}

        with patch.object(ai_remote, "execute_rpc_operation", side_effect=fake_execute):
            first, replayed_first = ai_remote.execute_rpc_call(
                call_id, "material.get_material", ["mat-1"], {}
            )
            second, replayed_second = ai_remote.execute_rpc_call(
                call_id, "material.get_material", ["mat-1"], {}
            )

        self.assertEqual(first, second)
        self.assertFalse(replayed_first)
        self.assertTrue(replayed_second)
        self.assertEqual(len(calls), 1)

    def test_unknown_rpc_operation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "允許清單"):
            ai_remote.execute_rpc_operation("os.system", ["whoami"], {})

    def test_control_plane_keeps_large_media_off_render(self):
        remote = ROOT.joinpath("teacher_app", "worker", "ai_remote.py").read_text(encoding="utf-8")
        routes = ROOT.joinpath("teacher_app", "worker", "routes.py").read_text(encoding="utf-8")
        worker = ROOT.joinpath("ai_question_worker.py").read_text(encoding="utf-8")
        env_example = ROOT.joinpath(".local-worker.env.example").read_text(encoding="utf-8")
        render = ROOT.joinpath("render.yaml").read_text(encoding="utf-8")
        run_ps1 = ROOT.joinpath("run_ai_worker_autostart.ps1").read_text(encoding="utf-8")

        for marker in (
            "queue.ai_questions",
            "queue.media_scripts",
            "queue.ai_presentations",
            "queue.ai_videos",
            "queue.media_audio",
            "queue.media_subtitles",
            "queue.touch",
        ):
            self.assertIn(marker, remote)
        self.assertIn("/api/ai-worker/heartbeat", routes)
        self.assertIn("/api/ai-worker/rpc", routes)
        self.assertIn("AI_WORKER_RPC_MAX_BYTES", routes)
        self.assertIn("control_transport={transport}", worker)
        self.assertIn("AI_WORKER_TRANSPORT=https", env_example)
        self.assertIn("AI_WORKER_TOKEN=", env_example)
        self.assertIn("AI_WORKER_TOKEN", render)
        self.assertIn("outbound HTTPS 443", run_ps1)
        self.assertNotIn("send_file(", remote)
        self.assertNotIn("upload_file(", remote)

    def test_windows_ai_worker_no_longer_requires_database_url_in_https_mode(self):
        run_ps1 = ROOT.joinpath("run_ai_worker_autostart.ps1").read_text(encoding="utf-8")
        setup_ps1 = ROOT.joinpath("setup_teacher_worker.ps1").read_text(encoding="utf-8")
        docs = ROOT.joinpath("docs", "windows-ai-worker.md").read_text(encoding="utf-8")
        self.assertIn('AI_WORKER_TRANSPORT = "https"', run_ps1)
        self.assertIn("direct database fallback is disabled", run_ps1)
        self.assertIn('if (-not $aiTransport) { $aiTransport = "https" }', setup_ps1)
        self.assertIn("direct PostgreSQL is not required", setup_ps1)
        self.assertIn("does **not** need direct Supabase PostgreSQL 5432/6543 access", docs)


if __name__ == "__main__":
    unittest.main()
