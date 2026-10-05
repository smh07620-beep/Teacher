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
