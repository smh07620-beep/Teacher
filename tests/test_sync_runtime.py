import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.config import StoragePaths
from teacher_app.materials.sync_runtime import (
    SyncMaterialRuntimeComposer,
    is_mega_capacity_full_error,
)


def _paths(root: Path) -> StoragePaths:
    material = root / "materials"
    return StoragePaths(
        base_dir=root,
        static_dir=root / "static",
        slides_dir=root / "static" / "slides",
        material_storage=material,
        upload_dir=material / "ppt",
        question_images_dir=material / "question_images",
        uploaded_slides_dir=material / "slides",
        doc_templates_dir=material / "doc_templates",
        pgy_assessment_templates_dir=material / "pgy_assessment_templates",
        data_dir=root / "data",
        tmp_dir=root / "tmp",
        upload_progress_dir=root / "tmp" / "upload_progress",
        preview_cache_dir=root / "tmp" / "preview_cache",
    )


class _Storage:
    single_preview = True
    free_only = True

    def active_backend(self):
        return "local"

    def slide_format(self, *_args):
        return "png"

    def upload_material_tree_to_gdrive(self, *_args, **_kwargs):
        return "source", "slides", {}

    def _mega_cleanup(self, _key):
        return None

    @staticmethod
    def _content_type(_path):
        return "application/octet-stream"

    @staticmethod
    def _slide_local_path(slides_dir, page_no):
        return Path(slides_dir) / f"slide-{page_no:02d}.png"


class SyncRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = _paths(Path(self.temp.name))
        for path in (
            self.paths.upload_progress_dir,
            self.paths.preview_cache_dir,
            self.paths.upload_dir,
            self.paths.uploaded_slides_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _composer(self, **kwargs):
        return SyncMaterialRuntimeComposer(
            lambda: self.paths,
            classify_uploaded_material=lambda *_args, **_kwargs: ("standard", "規則分類", ""),
            extract_pdf_text=lambda _path: "",
            storage_adapter=_Storage(),
            **kwargs,
        )

    def test_capacity_classifier_matches_historical_quota_markers(self):
        self.assertTrue(is_mega_capacity_full_error(RuntimeError("quota exceeded")))
        self.assertTrue(is_mega_capacity_full_error(RuntimeError("免費模式已鎖定")))
        self.assertFalse(is_mega_capacity_full_error(RuntimeError("network timeout")))

    def test_progress_store_is_bound_through_runtime(self):
        composer = self._composer()
        runtime = composer.build()
        runtime.set_progress("p1", 12, "轉換 Office 文件", "detail", current=1, total=2)
        payload = composer._progress_store().read("p1")
        self.assertEqual(payload["percent"], 12.0)
        self.assertEqual(payload["stage"], "轉換 Office 文件")
        self.assertEqual(payload["current"], 1)
        runtime.clear_progress("p1")
        self.assertIsNone(composer._progress_store().read("p1"))

    def test_r2_mutations_fail_closed_without_ledger_callbacks(self):
        composer = self._composer()
        source = self.paths.tmp_dir / "source.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "ledger callback"):
            composer._r2_put_file(source, "materials/m1/source.txt")
        with self.assertRaisesRegex(RuntimeError, "ledger delete callback"):
            composer.r2_delete_prefix("materials/m1/")

    def test_r2_upload_and_delete_use_provider_owner_and_accounting_callbacks(self):
        records = []
        deleted = []
        composer = self._composer(
            r2_record_object=lambda key, size: records.append((key, size)),
            r2_record_deleted=deleted.append,
        )
        source = self.paths.tmp_dir / "source.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"abc")
        slides = self.paths.tmp_dir / "slides"
        slides.mkdir(parents=True, exist_ok=True)
        (slides / "slide-01.png").write_bytes(b"slide")

        class Client:
            def __init__(self):
                self.uploads = []

            def upload_file(self, local, bucket, key, ExtraArgs=None):
                self.uploads.append((local, bucket, key, ExtraArgs))

            def list_objects_v2(self, **_kwargs):
                return {"IsTruncated": False, "Contents": [{"Key": "materials/m1/source.txt"}]}

            def delete_objects(self, **_kwargs):
                return None

        client = Client()
        with patch("teacher_app.materials.sync_runtime.providers.r2_client", return_value=client), patch(
            "teacher_app.materials.sync_runtime.providers.R2_BUCKET_NAME", "bucket"
        ):
            keys = composer.upload_material_tree_to_r2("m1", source, slides, 1)
            composer.r2_delete_prefix("materials/m1/")

        self.assertEqual(keys, ("materials/m1/source.txt", "materials/m1/slides"))
        self.assertEqual(len(client.uploads), 2)
        self.assertEqual(records[0], ("materials/m1/source.txt", 3))
        self.assertEqual(deleted, ["materials/m1/source.txt"])


if __name__ == "__main__":
    unittest.main()
