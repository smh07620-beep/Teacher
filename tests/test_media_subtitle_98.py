import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import release_contract
from teacher_app.frontend.assets import ASSET_MANIFEST
from teacher_app.materials import media_subtitle_runtime


ROOT = Path(__file__).resolve().parents[1]


class MediaSubtitle98Tests(unittest.TestCase):
    def test_release_contract_places_subtitles_after_ai_material_drafts(self):
        self.assertIn("0098-media-subtitles", release_contract.REQUIRED_MIGRATIONS)
        self.assertLess(
            release_contract.REQUIRED_MIGRATIONS.index("0097-ai-material-drafts"),
            release_contract.REQUIRED_MIGRATIONS.index("0098-media-subtitles"),
        )
        # 0098 remains a required ordered migration even after later additive
        # releases become the current release marker.
        self.assertLess(
            release_contract.REQUIRED_MIGRATIONS.index("0098-media-subtitles"),
            release_contract.REQUIRED_MIGRATIONS.index("0099-ai-presentations"),
        )

    def test_migration_is_additive_and_has_reviewed_caption_tables(self):
        # Read source instead of importing the migration here. The global migration
        # registry is order-sensitive and must be populated only by the production
        # factory/compatibility chain during normal test discovery.
        source = ROOT.joinpath("teacher_app", "maintenance", "media_subtitle_migration.py").read_text(encoding="utf-8")
        self.assertIn('@migration("0098-media-subtitles")', source)
        self.assertIn("CREATE TABLE IF NOT EXISTS media_subtitle_jobs", source)
        self.assertIn("CREATE TABLE IF NOT EXISTS media_subtitles", source)
        for marker in ("vtt_text", "srt_text", "provider", "model", "source_version", "source_sha256", "approved_by"):
            self.assertIn(marker, source)

    def test_segment_renderers_create_vtt_and_srt_timing(self):
        segments = [
            {"start": 0.25, "end": 2.5, "text": "第一句"},
            {"start": 3.0, "end": 5.125, "text": "第二句"},
        ]
        vtt = media_subtitle_runtime.segments_to_vtt(segments)
        srt = media_subtitle_runtime.segments_to_srt(segments)
        self.assertTrue(vtt.startswith("WEBVTT\n"))
        self.assertIn("00:00:00.250 --> 00:00:02.500", vtt)
        self.assertIn("00:00:03,000 --> 00:00:05,125", srt)
        self.assertIn("第一句", vtt)
        self.assertIn("第二句", srt)

    def test_external_media_disabled_uses_local_whisper_without_cloud_call(self):
        settings = SimpleNamespace(groq_api_key="groq-key", groq_transcribe_model="whisper-large-v3-turbo")
        local = SimpleNamespace(
            whisper_enabled=True,
            whisper_model="small",
            whisper_device="cpu",
            whisper_compute_type="int8",
        )
        expected = [{"start": 0.0, "end": 1.0, "text": "本機字幕"}]
        with patch.object(media_subtitle_runtime.ai_privacy, "external_enabled", return_value=True), \
             patch.object(media_subtitle_runtime.ai_privacy, "external_media_allowed", return_value=False), \
             patch.object(media_subtitle_runtime, "groq_transcribe_segments") as cloud, \
             patch.object(media_subtitle_runtime, "local_transcribe_segments", return_value=expected) as local_call:
            value, meta = media_subtitle_runtime.transcribe_segments(Path("audio.m4a"), settings=settings, local=local)
        self.assertEqual(value, expected)
        cloud.assert_not_called()
        local_call.assert_called_once()
        self.assertEqual(meta["provider"], "local-whisper")
        self.assertFalse(meta["fallbackUsed"])

    def test_retryable_cloud_failure_falls_back_to_local_but_validation_does_not(self):
        settings = SimpleNamespace(groq_api_key="groq-key", groq_transcribe_model="whisper-large-v3-turbo")
        local = SimpleNamespace(
            whisper_enabled=True,
            whisper_model="small",
            whisper_device="cpu",
            whisper_compute_type="int8",
        )
        expected = [{"start": 0.0, "end": 1.0, "text": "備援字幕"}]
        with patch.object(media_subtitle_runtime.ai_privacy, "external_enabled", return_value=True), \
             patch.object(media_subtitle_runtime.ai_privacy, "external_media_allowed", return_value=True), \
             patch.object(media_subtitle_runtime, "groq_transcribe_segments", side_effect=RuntimeError("429 rate limit")), \
             patch.object(media_subtitle_runtime, "local_transcribe_segments", return_value=expected):
            value, meta = media_subtitle_runtime.transcribe_segments(Path("audio.m4a"), settings=settings, local=local)
        self.assertEqual(value, expected)
        self.assertEqual(meta["provider"], "local-whisper")
        self.assertTrue(meta["fallbackUsed"])
        with patch.object(media_subtitle_runtime.ai_privacy, "external_enabled", return_value=True), \
             patch.object(media_subtitle_runtime.ai_privacy, "external_media_allowed", return_value=True), \
             patch.object(media_subtitle_runtime, "groq_transcribe_segments", side_effect=ValueError("validation failed")), \
             patch.object(media_subtitle_runtime, "local_transcribe_segments") as local_call:
            with self.assertRaises(ValueError):
                media_subtitle_runtime.transcribe_segments(Path("audio.m4a"), settings=settings, local=local)
        local_call.assert_not_called()

    def test_factory_worker_frontend_and_render_contracts_include_subtitles(self):
        factory = ROOT.joinpath("teacher_app", "factory.py").read_text(encoding="utf-8")
        worker = ROOT.joinpath("ai_question_worker.py").read_text(encoding="utf-8")
        render = ROOT.joinpath("render.yaml").read_text(encoding="utf-8")
        env = ROOT.joinpath(".local-ai-worker.env.example").read_text(encoding="utf-8")
        assets = ASSET_MANIFEST["/system"]
        self.assertIn("register_media_subtitle_routes", factory)
        self.assertIn("MediaSubtitleJobProcessor", worker)
        self.assertIn("requirements-ai-worker.txt", render)
        self.assertIn("MEDIA_SUBTITLE_LOCAL_WHISPER_ENABLED=true", env)
        self.assertIn("static/teacher-media-subtitles-98.js", assets)

    def test_route_source_requires_teacher_approval_and_current_source_version(self):
        source = ROOT.joinpath("teacher_app", "materials", "media_subtitle_routes.py").read_text(encoding="utf-8")
        self.assertIn("draft.get(\"status\") != \"approved\"", source)
        self.assertIn("sourceVersion", source)
        self.assertIn("sourceSha256", source)
        self.assertIn("_can_review", source)

    def test_worker_env_example_keeps_raw_media_local_by_default(self):
        env = ROOT.joinpath(".local-ai-worker.env.example").read_text(encoding="utf-8")
        self.assertIn("MEDIA_SUBTITLE_LOCAL_WHISPER_ENABLED=true", env)
        self.assertIn("MEDIA_SUBTITLE_CLOUD_FALLBACK_ENABLED=false", env)

    def test_youtube_and_vimeo_fail_closed_without_downloading_provider_media(self):
        source = ROOT.joinpath("teacher_app", "materials", "media_subtitle_runtime.py").read_text(encoding="utf-8")
        self.assertIn("YouTube / Vimeo", source)
        self.assertIn("不會下載第三方影音", source)
        self.assertNotIn("yt_dlp", source)
        self.assertNotIn("youtube_dl", source)


if __name__ == "__main__":
    unittest.main()
