from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

from teacher_app.materials import ai_video_jobs, ai_video_runtime, media_audio_runtime


class TtsCacheTests(unittest.TestCase):
    def test_key_normalizes_whitespace_and_binds_voice_repo_speed(self):
        first = media_audio_runtime.tts_cache_key("  教學\n內容 ", repo_id="repo-a", voice="zf_xiaoxiao", speed=1.0)
        self.assertEqual(first, media_audio_runtime.tts_cache_key("教學 內容", repo_id="repo-a", voice="zf_xiaoxiao", speed=1.0))
        self.assertNotEqual(first, media_audio_runtime.tts_cache_key("教學 內容", repo_id="repo-b", voice="zf_xiaoxiao", speed=1.0))
        self.assertNotEqual(first, media_audio_runtime.tts_cache_key("教學 內容", repo_id="repo-a", voice="zm_yunxi", speed=1.0))

    def test_valid_cached_wav_is_reused_without_pipeline(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"KOKORO_CACHE_DIR": temp, "KOKORO_REPO_ID": "repo-a"}, clear=False):
            key = media_audio_runtime.tts_cache_key("快取測試", repo_id="repo-a", voice="zf_xiaoxiao", speed=1.0)
            target = Path(temp) / f"{key}.wav"
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(b"R" * 1024)
            with patch.object(media_audio_runtime, "_kokoro_pipeline", side_effect=AssertionError("cache miss")):
                audio, _model = media_audio_runtime._synthesize("快取測試", voice="zf_xiaoxiao", instructions="")
        self.assertEqual(audio, b"R" * 1024)


class VideoEncodingTests(unittest.TestCase):
    def test_unchanged_deck_reuses_full_frame_cache(self):
        class Storage:
            def download(self, _location, target):
                target.write_bytes(b"immutable-pptx")
                return target
        slides = [{"id": "s1", "title": "A", "bullets": []}, {"id": "s2", "title": "B", "bullets": []}]
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"AI_VIDEO_CACHE_DIR": temp}, clear=False):
            first_root = Path(temp) / "first"; first_root.mkdir()
            frames = [first_root / "one.png", first_root / "two.png"]
            frames[0].write_bytes(b"one"); frames[1].write_bytes(b"two")
            with patch.object(ai_video_runtime.renderer, "render_exact_frames", return_value=(frames, "libreoffice-headless", [])) as render:
                ai_video_runtime._render_frames({}, slides, first_root, presentation_storage=Storage())
            second_root = Path(temp) / "second"; second_root.mkdir()
            with patch.object(ai_video_runtime.renderer, "render_exact_frames", side_effect=AssertionError("frame cache miss")):
                restored, selected, _attempts = ai_video_runtime._render_frames({}, slides, second_root, presentation_storage=Storage())
            restored_bytes = [item.read_bytes() for item in restored]
        render.assert_called_once()
        self.assertEqual(selected, "libreoffice-headless")
        self.assertEqual(restored_bytes, [b"one", b"two"])

    def test_segment_and_concat_commands_use_static_slide_profile_and_copy_concat(self):
        command = ai_video_runtime._segment_command(Path("slide.png"), Path("voice.wav"), Path("part.mp4"))
        self.assertIn("-framerate", command)
        self.assertIn("5", command)
        self.assertIn("veryfast", command)
        self.assertIn("stillimage", command)
        self.assertIn("23", command)
        self.assertIn("24000", command)
        concat = ai_video_runtime._concat_command(Path("concat.txt"), Path("out.mp4"))
        self.assertEqual(concat[concat.index("-c") + 1], "copy")
        self.assertIn("+faststart", concat)

    def test_segment_cache_hit_skips_encoding_and_reports_page_progress(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"AI_VIDEO_CACHE_DIR": temp}, clear=False):
            root = Path(temp) / "job"; root.mkdir()
            image, audio, output = root / "slide.png", root / "voice.wav", root / "out.mp4"
            image.write_bytes(b"image"); audio.write_bytes(b"audio")
            key = ai_video_runtime._segment_key(image, audio, encoder="libx264")
            cached = Path(temp) / "segments" / f"{key}.mp4"; cached.parent.mkdir(); cached.write_bytes(b"M" * 2048)
            calls, progress = [], []
            def run(command, **_kwargs):
                calls.append(command)
                Path(command[-1]).write_bytes(b"out")
            with patch.object(ai_video_runtime, "_run", side_effect=run):
                result = ai_video_runtime._compose_mp4(root, [{"image": image, "audio": audio}], output, progress_callback=lambda *args: progress.append(args))
        self.assertEqual(result["segmentCacheHits"], 1)
        self.assertEqual(len(calls), 1)  # concat only
        self.assertTrue(any(item[1] == "編碼投影片片段" for item in progress))
        self.assertTrue(any(item[1] == "無重編碼合併 MP4" for item in progress))

    def test_qsv_failure_retries_x264(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"AI_VIDEO_CACHE_DIR": temp}, clear=False):
            root = Path(temp) / "job"; root.mkdir()
            image, audio, output = root / "slide.png", root / "voice.wav", root / "out.mp4"
            image.write_bytes(b"image"); audio.write_bytes(b"audio")
            codecs = []
            def run(command, **_kwargs):
                if "-c:v" in command:
                    codec = command[command.index("-c:v") + 1]; codecs.append(codec)
                    if codec == "h264_qsv":
                        raise RuntimeError("qsv unavailable")
                Path(command[-1]).write_bytes(b"M" * 2048)
            with patch.object(ai_video_runtime, "_qsv_available", return_value=True), patch.object(ai_video_runtime, "_run", side_effect=run):
                result = ai_video_runtime._compose_mp4(root, [{"image": image, "audio": audio}], output)
        self.assertEqual(codecs, ["h264_qsv", "libx264"])
        self.assertEqual(result["encoder"], "libx264")


class VideoProgressTests(unittest.TestCase):
    def test_job_progress_callback_and_existing_heartbeat_can_coexist(self):
        job = {"id": "job-1", "status": "queued"}
        def generate(*, progress_callback, **_kwargs):
            progress_callback(42, "產生每頁 AI 語音", "第 1 頁")
            return {"videoId": "video-1"}
        with (
            patch.object(ai_video_jobs.repository, "claim", return_value=job),
            patch.object(ai_video_jobs.repository, "set_progress", return_value=True) as progress,
            patch.object(ai_video_jobs.repository, "complete") as complete,
            patch.object(ai_video_jobs.ai_video_runtime, "generate_video", side_effect=generate),
        ):
            self.assertTrue(ai_video_jobs.AiVideoJobProcessor().run_job("job-1"))
        progress.assert_called_with("job-1", ANY, 42, "產生每頁 AI 語音", "第 1 頁")
        complete.assert_called_once()


if __name__ == "__main__":
    unittest.main()
