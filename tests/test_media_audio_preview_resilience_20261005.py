import datetime as dt
import os
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from flask import Flask, g

from teacher_app.materials import media_audio_jobs, media_audio_repository, media_audio_runtime
from teacher_app.materials.media_audio_routes import register_media_audio_routes
from teacher_app.maintenance.media_audio_migration import media_audio_jobs_95


class MediaAudioPreviewResilienceTests(unittest.TestCase):
    def test_cached_preview_is_returned_without_queueing_worker_job(self):
        app = Flask(__name__)

        @app.before_request
        def bind_user():
            g.teacher_user = {
                "username": "teacher1",
                "roles": ["clinical_teacher"],
                "preferredGroup": "grpBio",
                "preferredArea": "internal",
            }

        register_media_audio_routes(app)
        cached = {
            "preview": True,
            "previewUrl": "https://r2.example/voice.wav",
            "voice": "zf_xiaoxiao",
            "mimeType": "audio/wav",
            "replayed": True,
        }
        with app.test_client() as client, \
             patch("teacher_app.materials.media_audio_routes.scope_filter.require_permission", return_value=None), \
             patch("teacher_app.materials.media_audio_routes.media_audio_runtime.cached_voice_preview", return_value=cached), \
             patch("teacher_app.materials.media_audio_routes.media_audio_jobs.enqueue_preview") as enqueue, \
             patch("teacher_app.materials.media_audio_routes.audit.record_event"):
            response = client.post("/api/media-audio/preview", json={"voice": "zf_xiaoxiao"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "completed")
        self.assertEqual(response.get_json()["result"]["mimeType"], "audio/wav")
        enqueue.assert_not_called()

    def test_uncached_preview_fails_fast_when_ai_worker_is_offline(self):
        app = Flask(__name__ + "-offline")

        @app.before_request
        def bind_user():
            g.teacher_user = {
                "username": "teacher1",
                "roles": ["clinical_teacher"],
                "preferredGroup": "grpBio",
                "preferredArea": "internal",
            }

        register_media_audio_routes(app)
        with app.test_client() as client, \
             patch("teacher_app.materials.media_audio_routes.scope_filter.require_permission", return_value=None), \
             patch("teacher_app.materials.media_audio_routes.media_audio_runtime.cached_voice_preview", return_value={}), \
             patch("teacher_app.materials.media_audio_routes._ai_worker_status", return_value={"online": False, "seen": False, "kokoroInstalled": None}), \
             patch("teacher_app.materials.media_audio_routes.media_audio_jobs.enqueue_preview") as enqueue:
            response = client.post("/api/media-audio/preview", json={"voice": "zf_xiaoxiao"})

        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.get_json()["workerOffline"])
        self.assertIn("AI Worker", response.get_json()["error"])
        enqueue.assert_not_called()

    def test_repeated_preview_click_reuses_same_active_voice_job(self):
        stamp = dt.datetime.now(dt.timezone.utc).isoformat()
        existing = {
            "id": "majob-existing",
            "status": "queued",
            "actorUsername": "teacher1",
            "updatedAt": stamp,
            "createdAt": stamp,
            "request": {"preview": True, "voice": "zf_xiaoxiao"},
        }
        actor = {"username": "teacher1", "preferredGroup": "grpBio", "preferredArea": "internal"}
        with patch.object(media_audio_runtime, "configured", return_value=True), \
             patch.object(media_audio_jobs.media_audio_repository, "expire_stale_previews", return_value=0), \
             patch.object(media_audio_jobs.media_audio_repository, "active_preview_job_for_actor", return_value=existing), \
             patch.object(media_audio_jobs.media_audio_repository, "create_job") as create:
            result = media_audio_jobs.enqueue_preview({"voice": "zf_xiaoxiao"}, actor)

        self.assertEqual(result["id"], "majob-existing")
        self.assertTrue(result["_reusedActive"])
        create.assert_not_called()

    def test_unclaimed_preview_becomes_clear_failure_and_unblocks_retry(self):
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)).isoformat()
        queued = {
            "id": "majob-stale",
            "status": "queued",
            "updatedAt": old,
            "createdAt": old,
            "request": {"preview": True, "voice": "zf_xiaoxiao"},
        }
        failed = {**queued, "status": "failed", "error": "本機 Kokoro AI Worker 尚未取得試聽工作"}
        with patch.object(media_audio_jobs.media_audio_repository, "fail_queued_preview", return_value=True) as fail, \
             patch.object(media_audio_jobs.media_audio_repository, "get_job", return_value=failed):
            result = media_audio_jobs.expire_unclaimed_preview(queued)

        self.assertEqual(result["status"], "failed")
        self.assertIn("Kokoro AI Worker", result["error"])
        fail.assert_called_once()

    def test_cached_runtime_response_declares_wav_mime(self):
        with patch.object(media_audio_runtime, "configured", return_value=True), \
             patch.object(media_audio_runtime.providers, "r2_client", return_value=object()), \
             patch.object(media_audio_runtime, "_existing_r2", return_value=2048), \
             patch.object(media_audio_runtime, "preview_url", return_value="https://r2.example/voice.wav"), \
             patch.object(media_audio_runtime.r2_ledger, "record_object"):
            result = media_audio_runtime.cached_voice_preview("zf_xiaoxiao")

        self.assertEqual(result["mimeType"], "audio/wav")
        self.assertEqual(result["previewUrl"], "https://r2.example/voice.wav")

    def test_preview_cache_identity_changes_with_repo_voice_text_and_speed(self):
        base_env = {
            "KOKORO_REPO_ID": "hexgrad/Kokoro-82M-v1.1-zh",
            "KOKORO_MODEL": "Kokoro-82M-v1.1-zh",
            "KOKORO_TTS_SPEED": "1.0",
        }
        with patch.dict(os.environ, base_env, clear=False):
            base = media_audio_runtime._preview_identity("zf_001")[2]
            repeated = media_audio_runtime._preview_identity("zf_001")[2]
            voice_changed = media_audio_runtime._preview_identity("zf_002")[2]
        with patch.dict(os.environ, {**base_env, "KOKORO_TTS_SPEED": "1.1"}, clear=False):
            speed_changed = media_audio_runtime._preview_identity("zf_001")[2]
        with patch.dict(os.environ, {**base_env, "KOKORO_REPO_ID": "example/alternate-kokoro"}, clear=False):
            repo_changed = media_audio_runtime._preview_identity("zf_001")[2]
        with patch.dict(os.environ, base_env, clear=False), \
             patch.object(media_audio_runtime, "VOICE_PREVIEW_TEXT", "不同的固定試聽文字"):
            text_changed = media_audio_runtime._preview_identity("zf_001")[2]

        self.assertEqual(base, repeated)
        self.assertNotEqual(base, voice_changed)
        self.assertNotEqual(base, speed_changed)
        self.assertNotEqual(base, repo_changed)
        self.assertNotEqual(base, text_changed)

    def test_repository_preview_lookup_and_timeout_are_compare_and_set(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        media_audio_jobs_95(conn, "sqlite")

        @contextmanager
        def read_connection():
            yield conn, "sqlite"

        @contextmanager
        def transaction():
            try:
                yield conn, "sqlite"
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        stamp = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)).isoformat()
        values = {
            "id": "majob-sql",
            "script_id": "",
            "material_id": "",
            "group_key": "grpBio",
            "training_area": "internal",
            "actor_username": "teacher1",
            "request": {"preview": True, "voice": "zf_xiaoxiao"},
            "created_at": stamp,
        }
        try:
            with patch.object(media_audio_repository.common_db, "read_connection", read_connection), \
                 patch.object(media_audio_repository.common_db, "transaction", transaction):
                media_audio_repository.create_job(values)
                active = media_audio_repository.active_preview_job_for_actor("teacher1")
                self.assertEqual(active["id"], "majob-sql")
                self.assertTrue(media_audio_repository.fail_queued_preview("majob-sql", active["updatedAt"], "worker offline"))
                self.assertFalse(media_audio_repository.fail_queued_preview("majob-sql", active["updatedAt"], "duplicate"))
                self.assertEqual(media_audio_repository.get_job("majob-sql")["status"], "failed")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
