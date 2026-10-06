import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from teacher_app.materials import job_commit
from teacher_app.worker.media_transcode_compat import transcode_if_needed


ROOT = Path(__file__).resolve().parents[1]


class FakeWorker:
    VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v"}
    AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg"}
    os = __import__("os")

    commands = []
    fail_encoder = ""

    class subprocess:
        TimeoutExpired = subprocess.TimeoutExpired

        @staticmethod
        def run(command, **_kwargs):
            FakeWorker.commands.append(list(command))
            if FakeWorker.fail_encoder and FakeWorker.fail_encoder in command:
                return SimpleNamespace(returncode=1, stderr="hardware encoder failed")
            target = Path(command[-1])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"normalized-media")
            return SimpleNamespace(returncode=0, stderr="")

    @staticmethod
    def _bin(_env_name, _fallback):
        return "ffmpeg"

    probe = {
        "durationSeconds": 30.0,
        "width": 0,
        "height": 0,
        "bitrate": 64000,
        "videoCodec": "",
        "audioCodec": "opus",
    }

    @classmethod
    def _probe_media(cls, _source):
        return dict(cls.probe)


class TeacherRecorderWebmAudio1014Tests(unittest.TestCase):
    def setUp(self):
        FakeWorker.commands = []
        FakeWorker.fail_encoder = ""
        self.env = patch.dict(
            os.environ,
            {
                "MATERIAL_VIDEO_HARDWARE_ACCELERATION": "false",
                "MATERIAL_VIDEO_HARDWARE_ENCODER": "auto",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_audio_only_webm_uses_audio_transcode_path(self):
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            source = temp / "source.webm"
            source.write_bytes(b"webm-audio")
            FakeWorker.probe = {
                "durationSeconds": 30.0,
                "width": 0,
                "height": 0,
                "bitrate": 64000,
                "videoCodec": "",
                "audioCodec": "opus",
            }
            output, name, metadata, derivatives = transcode_if_needed(
                FakeWorker, source, "老師錄音.webm", temp
            )
            self.assertEqual(output.name, "web.m4a")
            self.assertEqual(name, "老師錄音.m4a")
            self.assertEqual(metadata["mediaKind"], "audio")
            self.assertEqual(metadata["sourceOriginalName"], "老師錄音.webm")
            self.assertNotIn("videoCrf", metadata)
            self.assertEqual(derivatives, {})

    def test_webm_with_video_stream_stays_video(self):
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            source = temp / "source.webm"
            source.write_bytes(b"webm-video")
            FakeWorker.probe = {
                "durationSeconds": 30.0,
                "width": 1280,
                "height": 720,
                "bitrate": 500000,
                "videoCodec": "vp8",
                "audioCodec": "opus",
            }
            output, name, metadata, derivatives = transcode_if_needed(
                FakeWorker, source, "老師錄影.webm", temp
            )
            self.assertEqual(output.name, "web.mp4")
            self.assertEqual(name, "老師錄影.mp4")
            self.assertEqual(metadata["mediaKind"], "video")
            self.assertEqual(metadata["videoCrf"], 23)
            self.assertIn("poster.webp", derivatives)
            self.assertIn("audio.m4a", derivatives)

    def test_web_safe_mp4_uses_fast_remux_instead_of_h264_reencode(self):
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            source = temp / "source.mp4"
            source.write_bytes(b"mp4-video")
            FakeWorker.probe = {
                "durationSeconds": 30.0,
                "width": 1280,
                "height": 720,
                "bitrate": 900000,
                "videoCodec": "h264",
                "audioCodec": "aac",
            }
            _output, _name, metadata, _derivatives = transcode_if_needed(
                FakeWorker, source, "已最佳化影片.mp4", temp
            )
            first = FakeWorker.commands[0]
            self.assertIn("copy", first)
            self.assertNotIn("libx264", first)
            self.assertEqual(metadata["transcodeMode"], "remux")
            self.assertNotIn("videoCrf", metadata)

    def test_large_h264_video_still_uses_safe_transcode(self):
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            source = temp / "source.mp4"
            source.write_bytes(b"mp4-video")
            FakeWorker.probe = {
                "durationSeconds": 30.0,
                "width": 1920,
                "height": 1080,
                "bitrate": 3000000,
                "videoCodec": "h264",
                "audioCodec": "aac",
            }
            transcode_if_needed(FakeWorker, source, "1080p.mp4", temp)
            first = FakeWorker.commands[0]
            self.assertIn("libx264", first)
            self.assertIn("veryfast", first)

    def test_hardware_encoder_is_used_after_probe_selection(self):
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            source = temp / "source.mov"
            source.write_bytes(b"mov-video")
            FakeWorker.probe = {
                "durationSeconds": 30.0,
                "width": 1920,
                "height": 1080,
                "bitrate": 3000000,
                "videoCodec": "h264",
                "audioCodec": "aac",
            }
            with patch(
                "teacher_app.worker.media_transcode_compat.media_acceleration.detect_h264_encoder",
                return_value={
                    "enabled": True,
                    "available": True,
                    "selected": "h264_qsv",
                    "selectedKind": "qsv",
                    "preference": "auto",
                },
            ):
                _output, _name, metadata, _derivatives = transcode_if_needed(
                    FakeWorker, source, "1080p.mov", temp
                )
            first = FakeWorker.commands[0]
            self.assertIn("h264_qsv", first)
            self.assertNotIn("libx264", first)
            self.assertEqual(metadata["transcodeMode"], "hardware")
            self.assertEqual(metadata["hardwareEncoderUsed"], "h264_qsv")

    def test_hardware_encoder_failure_falls_back_to_cpu_for_same_job(self):
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            source = temp / "source.mov"
            source.write_bytes(b"mov-video")
            FakeWorker.probe = {
                "durationSeconds": 30.0,
                "width": 1920,
                "height": 1080,
                "bitrate": 3000000,
                "videoCodec": "h264",
                "audioCodec": "aac",
            }
            FakeWorker.fail_encoder = "h264_qsv"
            with patch(
                "teacher_app.worker.media_transcode_compat.media_acceleration.detect_h264_encoder",
                return_value={
                    "enabled": True,
                    "available": True,
                    "selected": "h264_qsv",
                    "selectedKind": "qsv",
                    "preference": "auto",
                },
            ):
                _output, _name, metadata, _derivatives = transcode_if_needed(
                    FakeWorker, source, "1080p.mov", temp
                )
            self.assertIn("h264_qsv", FakeWorker.commands[0])
            self.assertTrue(any("libx264" in command for command in FakeWorker.commands))
            self.assertEqual(metadata["transcodeMode"], "transcode")
            self.assertEqual(metadata["hardwareEncoderAttempted"], "h264_qsv")
            self.assertIn("hardware encoder failed", metadata["hardwareFallback"])

    def test_job_commit_uses_normalized_audio_suffix_for_viewer(self):
        job = {
            "materialId": "mat-recorder-audio",
            "payload": {
                "originalName": "老師錄音.webm",
                "title": "老師錄音",
                "group": "grpBio",
                "area": "internal",
                "courseId": "course-1",
                "materialType": "standard",
            },
        }
        result = {
            "storageBackend": "mega",
            "storageKey": "/materials/mat-recorder-audio/source.m4a",
            "storageFilename": "source.m4a",
            "pageCount": 0,
            "storageMeta": {
                "mediaKind": "audio",
                "sourceOriginalName": "老師錄音.webm",
                "audioCodec": "opus",
            },
        }
        with patch.object(job_commit.material_repository, "get_material", return_value=None), \
             patch.object(job_commit.material_repository, "insert_material") as insert:
            entry = job_commit.commit(job, result)
        self.assertEqual(entry["filename"], "老師錄音.m4a")
        self.assertEqual(entry["storage_filename"], "source.m4a")
        inserted = insert.call_args.args[0]
        self.assertEqual(inserted["filename"], "老師錄音.m4a")

    def test_worker_resolved_auto_classification_is_persisted(self):
        job = {
            "materialId": "mat-auto-sop",
            "payload": {
                "originalName": "SOP.docx",
                "title": "生化 SOP",
                "group": "grpBio",
                "area": "internal",
                "courseId": "course-1",
                "materialType": "auto",
            },
        }
        result = {
            "storageBackend": "r2",
            "storageKey": "materials/mat-auto-sop/source.docx",
            "storageFilename": "source.docx",
            "slidesPrefix": "materials/mat-auto-sop/slides",
            "pageCount": 3,
            "storageMeta": {"slideFormat": "png"},
            "materialType": "sop",
            "classificationMethod": "內容規則判斷",
            "classificationReason": "SOP 關鍵字明確",
        }
        with patch.object(job_commit.material_repository, "get_material", return_value=None), \
             patch.object(job_commit.material_repository, "insert_material") as insert:
            entry = job_commit.commit(job, result)
        inserted = insert.call_args.args[0]
        self.assertEqual(entry["material_type"], "sop")
        self.assertEqual(inserted["material_type"], "sop")
        self.assertIn('"resolved": "sop"', inserted["storage_meta"])
        self.assertNotEqual(inserted["material_type"], "auto")

    def test_private_ai_authoring_upload_stays_inactive_after_worker_commit(self):
        job = {
            "materialId": "mat-ai-private",
            "payload": {
                "originalName": "source.txt",
                "title": "私人 AI 來源",
                "group": "grpBio",
                "area": "internal",
                "courseId": "",
                "materialType": "standard",
                "authoringOnly": True,
            },
        }
        result = {
            "storageBackend": "r2",
            "storageKey": "materials/mat-ai-private/source.txt",
            "storageFilename": "source.txt",
            "pageCount": 0,
            "storageMeta": {},
        }
        with patch.object(job_commit.material_repository, "get_material", return_value=None), \
             patch.object(job_commit.material_repository, "insert_material") as insert:
            entry = job_commit.commit(job, result)
        inserted = insert.call_args.args[0]
        self.assertFalse(inserted["active"])
        self.assertFalse(entry["active"])

    def test_windows_supervisor_uses_packaged_media_safe_entrypoint(self):
        source = ROOT.joinpath("run_material_worker_autostart.ps1").read_text(encoding="utf-8")
        entry = ROOT.joinpath("teacher_app", "worker", "material_worker_entry.py").read_text(encoding="utf-8")
        self.assertIn("-m teacher_app.worker.material_worker_entry", source)
        self.assertIn("media_transcode_compat import install", entry)
        self.assertIn("install(worker)", entry)
        self.assertIn("worker.main()", entry)
        self.assertFalse(ROOT.joinpath("material_worker_entry.py").exists())


if __name__ == "__main__":
    unittest.main()
