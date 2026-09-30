from __future__ import annotations

import io
import shutil
import sqlite3
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from teacher_app.materials import ai_video_jobs, ai_video_runtime
from teacher_app.materials.ai_video_routes import _artifact_ready, _video_allowed


def _migration():
    from teacher_app.maintenance import ai_video_migration
    return ai_video_migration


class AiVideoMigrationTests(unittest.TestCase):
    def test_0101_creates_additive_job_revision_and_receipt_tables(self):
        conn = sqlite3.connect(":memory:")
        _migration().ai_presentation_videos_101(conn, "sqlite")
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"ai_video_jobs", "ai_presentation_videos", "ai_video_publications"}.issubset(tables))
        columns = {row[1] for row in conn.execute("PRAGMA table_info(ai_presentation_videos)")}
        self.assertTrue({"presentation_id", "presentation_revision", "artifact_sha256", "duration_seconds", "timeline_json", "approved_by"}.issubset(columns))


class AiVideoRbacTests(unittest.TestCase):
    def test_system_admin_can_operate_but_never_teacher_approve(self):
        user = {"role": "system_admin"}
        self.assertTrue(_video_allowed(user, "video.create"))
        self.assertTrue(_video_allowed(user, "video.publish"))
        self.assertFalse(_video_allowed(user, "video.approve"))

    def test_teacher_and_group_leader_can_approve(self):
        for role in ("clinical_teacher", "group_leader"):
            self.assertTrue(_video_allowed({"role": role}, "video.approve"))


class AiVideoRuntimeTests(unittest.TestCase):
    def test_speaker_notes_are_the_first_narration_source(self):
        self.assertEqual(ai_video_runtime.narration_for_slide({"title": "T", "bullets": ["B"], "speakerNotes": "老師講稿"}), "老師講稿")

    def test_slide_text_is_safe_fallback_narration(self):
        self.assertEqual(ai_video_runtime.narration_for_slide({"title": "CBC", "bullets": ["確認 QC", "判讀結果"]}), "CBC。確認 QC。判讀結果")

    def test_secret_or_local_path_never_reaches_narration(self):
        for value in ("token=do-not-embed", r"C:\\Users\\worker\\secret"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ai_video_runtime.narration_for_slide({"speakerNotes": value})

    def test_artifact_must_be_shared_complete_mp4(self):
        artifact = {"artifactBackend": "r2", "artifactStorageKey": "ai-videos/a.mp4", "artifactSha256": "a" * 64, "artifactBytes": 4096, "artifactMimeType": "video/mp4", "durationSeconds": 8.2}
        self.assertTrue(_artifact_ready(artifact))
        self.assertFalse(_artifact_ready({**artifact, "artifactBackend": "local"}))
        self.assertFalse(_artifact_ready({**artifact, "artifactMimeType": "video/webm"}))

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is installed only on the AI Worker")
    def test_worker_vertical_slice_makes_mp4_timeline_and_captions(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(24000)
            output.writeframes(b"\0\0" * 24000)
        presentation = {
            "id": "ppt-1", "status": "approved", "group": "g", "area": "a", "title": "CBC 教學",
            "presentationFamilyId": "family-1", "revisionNumber": 2, "artifactBackend": "r2", "artifactStorageKey": "ppt.pptx",
            "artifactSha256": "a" * 64, "artifactBytes": 4096,
            "artifactMimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "slides": [{"id": "s1", "enabled": True, "title": "CBC", "bullets": ["確認 QC"], "speakerNotes": "先確認品質管制"}],
        }
        class Storage:
            def store(self, path, **_kwargs):
                return {"backend": "r2", "key": "ai-videos/test.mp4", "filename": "test.mp4", "sha256": "b" * 64, "byteSize": Path(path).stat().st_size, "mimeType": "video/mp4"}
        class PresentationStorage:
            def download(self, _location, target):
                target = Path(target)
                target.write_bytes(b"phase6-test-pptx")
                return target
        created = {
            "id": "vid-1", "artifactSha256": "b" * 64, "artifactBytes": 100, "durationSeconds": 2,
            "qualityManifest": {"status": "warning"}, "frameRenderer": "text-fallback",
        }
        renderer_attempts = [
            {"renderer": "powerpoint-com", "status": "failed", "detail": "test"},
            {"renderer": "libreoffice-headless", "status": "failed", "detail": "test"},
        ]
        with (
            patch.object(ai_video_runtime.repository, "get_video_by_source_job", return_value=None),
            patch.object(ai_video_runtime.presentation_repository, "get_presentation", return_value=presentation),
            patch.object(ai_video_runtime, "_synthesize", return_value=(audio.getvalue(), "Kokoro-test")),
            patch.object(ai_video_runtime.renderer, "render_exact_frames", return_value=([], "", renderer_attempts)),
            patch.object(ai_video_runtime.repository, "create_video", return_value=created) as create,
        ):
            result = ai_video_runtime.generate_video(
                job={"id": "vidjob-1", "presentationId": "ppt-1", "group": "g", "area": "a", "actorUsername": "teacher", "request": {}},
                storage=Storage(), presentation_storage=PresentationStorage(),
            )
        self.assertEqual(result["videoId"], "vid-1")
        kwargs = create.call_args.kwargs
        self.assertEqual(len(kwargs["timeline"]), 2)
        self.assertEqual(kwargs["timeline"][0]["slideId"], "phase4-cover")
        self.assertIn("WEBVTT", kwargs["vtt_text"])
        self.assertIn("先確認品質管制", kwargs["srt_text"])
        self.assertEqual(kwargs["frame_renderer"], "text-fallback")
        self.assertEqual(kwargs["render_metrics"]["rendererAttempts"][-1]["renderer"], "text-fallback")


class AiVideoQueueTests(unittest.TestCase):
    def test_worker_dispatches_video_only_to_worker_runtime(self):
        processor = ai_video_jobs.AiVideoJobProcessor()
        claimed = {"id": "vidjob-1", "presentationId": "ppt-1", "request": {"voice": "zf_xiaoxiao"}}
        with (
            patch.object(ai_video_jobs.repository, "claim", return_value=claimed),
            patch.object(ai_video_jobs.repository, "complete", return_value=True) as complete,
            patch.object(ai_video_jobs.ai_video_runtime, "generate_video", return_value={"videoId": "vid-1"}) as generate,
        ):
            self.assertTrue(processor.run_job("vidjob-1"))
        generate.assert_called_once()
        complete.assert_called_once()

    def test_only_approved_presentation_enters_runtime(self):
        job = {"id": "vidjob-1", "presentationId": "ppt-1", "group": "g", "area": "a", "request": {}}
        with (
            patch.object(ai_video_runtime.repository, "get_video_by_source_job", return_value=None),
            patch.object(ai_video_runtime.presentation_repository, "get_presentation", return_value={"id": "ppt-1", "status": "draft"}),
        ):
            with self.assertRaisesRegex(RuntimeError, "已由授課教師核准"):
                ai_video_runtime.generate_video(job=job)


if __name__ == "__main__":
    unittest.main()
