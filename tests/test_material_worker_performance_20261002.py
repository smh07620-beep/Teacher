import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import material_worker
from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter


class MaterialWorkerPerformance20261002Tests(unittest.TestCase):
    def test_default_claim_poll_is_two_seconds(self):
        source = Path(material_worker.__file__).read_text(encoding="utf-8")
        self.assertIn('MATERIAL_WORKER_POLL_SECONDS","2"', source)

    def test_publish_reuses_prepared_office_pdf_and_records_timings(self):
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            source = temp / "source.ppt"
            source.write_bytes(b"legacy-office")
            prepared = temp / "prepared.pdf"
            prepared.write_bytes(b"%PDF-prepared")

            fake = Mock()
            fake.single_preview = True
            fake.active_backend.return_value = "mega"
            fake.prepare_office_pdf.return_value = prepared

            def convert_preview(pdf_path, _slides, *, progress_callback=None):
                self.assertEqual(Path(pdf_path), prepared)
                if progress_callback:
                    progress_callback(1, 2)
                    progress_callback(2, 2)
                return 2

            fake.convert_pdf_to_images.side_effect = convert_preview
            fake.upload_material_tree_to_mega.return_value = (
                "/root/material/source.ppt",
                "/root/material/slides",
                {"adapter": "megacmd", "slideFormat": "webp"},
            )
            timings = {}
            with patch.object(material_worker, "STORAGE", fake), \
                 patch.object(material_worker, "_transcode_if_needed", return_value=(source, "source.ppt", {}, {})), \
                 patch.object(material_worker, "_build_text_index", return_value=(None, {"textIndexAvailable": False})):
                result = material_worker.publish_to_storage(
                    source,
                    "source.ppt",
                    {"id": "job-1", "materialId": "mat-1"},
                    temp,
                    "a" * 64,
                    timings=timings,
                )

            fake.prepare_office_pdf.assert_called_once()
            fake.convert_pdf_to_images.assert_called_once()
            fake.build_single_preview_pdf.assert_not_called()
            self.assertEqual(result["pageCount"], 2)
            self.assertIn("officeToPdfMs", timings)
            self.assertIn("textIndexMs", timings)
            self.assertIn("renderAndProviderMs", timings)
            self.assertEqual(result["storageMeta"]["workerTimingsMs"], timings)

    def test_publish_maps_real_page_and_r2_byte_progress(self):
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            source = temp / "source.pdf"
            source.write_bytes(b"%PDF-progress")
            fake = Mock()
            fake.single_preview = False
            fake.active_backend.return_value = "r2"

            def convert(_pdf, _slides, *, progress_callback=None):
                if progress_callback:
                    progress_callback(1, 4)
                    progress_callback(2, 4)
                    progress_callback(4, 4)
                return 4

            def upload(_material_id, _source, _slides, _pages, **kwargs):
                callback = kwargs.get("progress_callback")
                if callback:
                    callback(25, 100, "原始教材")
                    callback(50, 100, "預覽第 2/4 頁")
                    callback(100, 100, "預覽第 4/4 頁")
                return (
                    "materials/mat-1/source.pdf",
                    "materials/mat-1/slides",
                    {"r2Objects": [{"key": "materials/mat-1/source.pdf", "bytes": 13}]},
                )

            fake.convert_pdf_to_images.side_effect = convert
            fake.upload_material_tree_to_r2.side_effect = upload
            events = []
            with patch.object(material_worker, "STORAGE", fake), \
                 patch.object(material_worker, "_transcode_if_needed", return_value=(source, "source.pdf", {}, {})), \
                 patch.object(material_worker, "_build_text_index", return_value=(None, {"textIndexAvailable": False})):
                material_worker.publish_to_storage(
                    source,
                    "source.pdf",
                    {"id": "job-progress", "materialId": "mat-1"},
                    temp,
                    "a" * 64,
                    progress_callback=lambda stage, detail="", percent=None: events.append(
                        (stage, detail, percent)
                    ),
                )

        page_percents = [percent for stage, _detail, percent in events if stage == "建立預覽" and percent]
        upload_percents = [percent for stage, _detail, percent in events if stage == "正式發布" and percent]
        self.assertIn(84, page_percents)
        self.assertIn(92, upload_percents)
        self.assertTrue(any("第 4/4 頁" in detail for stage, detail, _percent in events if stage == "建立預覽"))
        self.assertTrue(any("R2 正式上傳" in detail for stage, detail, _percent in events if stage == "正式發布"))

    def test_publish_maps_ffmpeg_time_progress_into_worker_percent(self):
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            original = temp / "source.mov"
            original.write_bytes(b"video")
            normalized = temp / "web.mp4"
            normalized.write_bytes(b"normalized")

            fake = Mock()
            fake.single_preview = False
            fake.active_backend.return_value = "r2"
            fake.upload_media_bundle_to_r2.return_value = (
                "materials/mat-video/source.mp4",
                "",
                {"r2Objects": [{"key": "materials/mat-video/source.mp4", "bytes": 10}]},
            )

            def transcode(_source, _original, _temp, *, progress_callback=None):
                self.assertIsNotNone(progress_callback)
                progress_callback(300, 600, "影片 CPU 轉碼")
                progress_callback(600, 600, "影片 CPU 轉碼")
                return (
                    normalized,
                    "source.mp4",
                    {"mediaKind": "video", "durationSeconds": 600},
                    {},
                )

            events = []
            with patch.object(material_worker, "STORAGE", fake), \
                 patch.object(material_worker, "_transcode_if_needed", side_effect=transcode), \
                 patch.object(material_worker, "_build_text_index", return_value=(None, {})):
                material_worker.publish_to_storage(
                    original,
                    "source.mov",
                    {"id": "job-video", "materialId": "mat-video"},
                    temp,
                    "a" * 64,
                    progress_callback=lambda stage, detail="", percent=None: events.append(
                        (stage, detail, percent)
                    ),
                )

        media_events = [
            (detail, percent)
            for stage, detail, percent in events
            if stage == "轉檔處理" and "影片 CPU 轉碼" in detail
        ]
        self.assertTrue(media_events)
        self.assertTrue(any("50%" in detail for detail, _percent in media_events))
        self.assertTrue(any("05:00 / 10:00" in detail for detail, _percent in media_events))
        self.assertIn(70, [percent for _detail, percent in media_events])
        self.assertIn(75, [percent for _detail, percent in media_events])

    def test_mega_preview_bundle_ensures_material_folder_once(self):
        runtime = WorkerMaterialStorageAdapter()
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            source = temp / "source.pdf"
            preview = temp / "preview.pdf"
            index = temp / "index.txt"
            source.write_bytes(b"source")
            preview.write_bytes(b"preview")
            index.write_text("index", encoding="utf-8")
            ensured = []

            def ensure(path):
                ensured.append(str(path))
                return str(path)

            def run(_args, **_kwargs):
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with patch.object(runtime, "_mega_root", return_value="/root"), \
                 patch.object(runtime, "_mega_login"), \
                 patch.object(runtime, "_mega_free_guard"), \
                 patch.object(runtime, "_mega_ensure_dir", side_effect=ensure), \
                 patch.object(runtime, "_mega_run", side_effect=run):
                runtime.upload_material_preview_to_mega(
                    "mat-1",
                    source,
                    preview,
                    2,
                    {"index.txt": index},
                )

            self.assertEqual(ensured, ["/root/mat-1"])


if __name__ == "__main__":
    unittest.main()
