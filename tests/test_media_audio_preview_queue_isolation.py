import unittest
from unittest.mock import patch

from teacher_app.materials import media_audio_jobs


class MediaAudioPreviewQueueIsolationTests(unittest.TestCase):
    def test_formal_audio_job_does_not_block_voice_preview(self):
        with patch.object(media_audio_jobs.media_audio_repository,"active_preview_count_for_actor",return_value=0), \
             patch.object(media_audio_jobs.media_audio_repository,"total_active_preview_count",return_value=0), \
             patch.object(media_audio_jobs.media_audio_repository,"recent_preview_count_for_actor",return_value=0), \
             patch.object(media_audio_jobs.media_audio_repository,"active_formal_count_for_actor",return_value=1):
            media_audio_jobs._enforce_queue_limits("teacher",preview=True)

    def test_preview_jobs_do_not_block_formal_narration(self):
        with patch.object(media_audio_jobs.media_audio_repository,"active_formal_count_for_actor",return_value=0), \
             patch.object(media_audio_jobs.media_audio_repository,"total_active_formal_count",return_value=0), \
             patch.object(media_audio_jobs.media_audio_repository,"recent_formal_count_for_actor",return_value=0), \
             patch.object(media_audio_jobs.media_audio_repository,"active_preview_count_for_actor",return_value=3):
            media_audio_jobs._enforce_queue_limits("teacher",preview=False)

    def test_same_voice_preview_reuses_existing_inflight_job(self):
        existing = {
            "id": "majob-existing",
            "actorUsername": "teacher",
            "request": {"preview": True, "voice": "zf_xiaoxiao"},
            "status": "queued",
        }
        prepared = {
            "id": "majob-new",
            "actor_username": "teacher",
            "request": {"preview": True, "voice": "zf_xiaoxiao"},
        }
        with patch.object(media_audio_jobs.media_audio_runtime, "configured", return_value=True), \
             patch.object(media_audio_jobs, "prepare_preview_request", return_value=prepared), \
             patch.object(media_audio_jobs.media_audio_repository, "expire_stale_previews", return_value=0) as expire, \
             patch.object(media_audio_jobs.media_audio_repository, "active_preview_job_for_actor", return_value=existing), \
             patch.object(media_audio_jobs.media_audio_repository, "create_job") as create:
            result = media_audio_jobs.enqueue_preview({"voice": "zf_xiaoxiao"}, {"username": "teacher"})
        self.assertEqual(result["id"], "majob-existing")
        self.assertTrue(result["_reusedActive"])
        expire.assert_called_once()
        create.assert_not_called()

    def test_preview_limit_message_is_preview_specific(self):
        with patch.object(media_audio_jobs.media_audio_repository,"active_preview_count_for_actor",return_value=3), \
             patch.object(media_audio_jobs.media_audio_repository,"total_active_preview_count",return_value=3), \
             patch.object(media_audio_jobs.media_audio_repository,"recent_preview_count_for_actor",return_value=0):
            with self.assertRaises(media_audio_jobs.MediaAudioLimitError) as caught:
                media_audio_jobs._enforce_queue_limits("teacher",preview=True)
        self.assertIn("語音試聽",str(caught.exception))
        self.assertNotIn("正式 AI 語音",str(caught.exception))


if __name__=="__main__":
    unittest.main()
