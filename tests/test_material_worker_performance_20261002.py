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

            def build_preview(_source, output, *, prepared_pdf=None):
                self.assertEqual(Path(prepared_pdf), prepared)
                Path(output).write_bytes(b"%PDF-preview")
                return 2

            fake.build_single_preview_pdf.side_effect = build_preview
            fake.upload_material_preview_to_mega.return_value = (
                "/root/material/source.ppt",
                "/root/material",
                {"adapter": "megacmd"},
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
            self.assertEqual(result["pageCount"], 2)
            self.assertIn("officeToPdfMs", timings)
            self.assertIn("textIndexMs", timings)
            self.assertIn("renderAndProviderMs", timings)
            self.assertEqual(result["storageMeta"]["workerTimingsMs"], timings)

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
