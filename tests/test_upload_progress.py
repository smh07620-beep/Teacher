import json
import tempfile
import unittest
from pathlib import Path

from teacher_app.config import StoragePaths
from teacher_app.materials.upload_progress import UploadProgressStore


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


class UploadProgressStoreTests(unittest.TestCase):
    def test_set_read_clear_preserves_legacy_shape_and_sanitizes_id(self):
        with tempfile.TemporaryDirectory() as temp:
            store = UploadProgressStore(_paths(Path(temp)))
            store.set("../../progress:abc", 101.27, "轉換中", "detail", current=2, total=3)
            path = store.path("../../progress:abc")
            self.assertEqual(path.name, "progressabc.json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["percent"], 100)
            self.assertEqual(payload["stage"], "轉換中")
            self.assertEqual(payload["detail"], "detail")
            self.assertEqual(payload["current"], 2)
            self.assertEqual(payload["total"], 3)
            self.assertTrue(payload["updatedAt"])
            self.assertEqual(store.read("../../progress:abc"), payload)
            store.clear("../../progress:abc")
            self.assertIsNone(store.read("../../progress:abc"))

    def test_invalid_json_reads_as_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            store = UploadProgressStore(_paths(Path(temp)))
            path = store.path("p1")
            path.write_text("not-json", encoding="utf-8")
            self.assertIsNone(store.read("p1"))


if __name__ == "__main__":
    unittest.main()
