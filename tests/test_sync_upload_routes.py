import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g, jsonify

from teacher_app.config import StoragePaths
from teacher_app.materials import sync_upload
from teacher_app.materials.sync_upload_routes import register_sync_upload_routes


class _Base:
    def __init__(self, app):
        self.app = app
        self.allowed = True

    def require_admin(self):
        return None if self.allowed else (jsonify({"error": "denied"}), 403)


def _paths(root: Path) -> StoragePaths:
    material = root / "materials"
    paths = StoragePaths(
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
    for directory in (paths.upload_dir, paths.uploaded_slides_dir, paths.preview_cache_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def _runtime(paths, *, backend="r2", upload_error=None, classify=None, progress=None, deleted=None):
    progress = progress if progress is not None else []
    deleted = deleted if deleted is not None else []

    def upload_r2(material_id, source, slides, page_count):
        if upload_error:
            raise upload_error
        return f"materials/{material_id}/source{source.suffix}", f"materials/{material_id}/slides"

    return sync_upload.SyncUploadRuntime(
        paths_provider=lambda: paths,
        active_material_backend=lambda: backend,
        classify_uploaded_material=classify or (lambda *args, **kwargs: ("standard", "規則分類", "")),
        extract_pdf_text=lambda path: "",
        build_single_preview_pdf=lambda *args, **kwargs: 1,
        convert_pdf_to_images=lambda *args, **kwargs: 1,
        convert_office_to_images=lambda *args, **kwargs: 1,
        slide_format=lambda *args: "png",
        upload_material_preview_to_mega=lambda *args, **kwargs: ("mega-source", "mega-folder", {"folderId": "mega-folder"}),
        upload_material_tree_to_mega=lambda *args, **kwargs: ("mega-source", "mega-folder", {"folderId": "mega-folder"}),
        upload_material_tree_to_oci=lambda *args, **kwargs: ("oci-source", "oci-slides"),
        upload_material_tree_to_gdrive=lambda *args, **kwargs: ("drive-source", "drive-slides", {}),
        upload_material_tree_to_r2=upload_r2,
        mega_failover_ready=lambda: "",
        is_mega_capacity_full_error=lambda exc: False,
        mega_destroy=lambda key: deleted.append(("mega", key)),
        r2_delete_prefix=lambda key: deleted.append(("r2", key)),
        preview_cache_cleanup=lambda **kwargs: None,
        set_progress=lambda *args, **kwargs: progress.append(args),
        clear_progress=lambda progress_id: progress.append(("clear", progress_id)),
        single_preview_enabled=True,
    )


class SyncUploadRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = _paths(Path(self.temp.name))
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.base = _Base(self.app)

    def _register(self, runtime):
        register_sync_upload_routes(self.base, runtime=runtime)
        return self.app.test_client()

    def test_exact_endpoint_and_missing_file_contract(self):
        client = self._register(_runtime(self.paths))
        self.assertIn("api_upload_slide", self.app.view_functions)
        rules = [rule for rule in self.app.url_map.iter_rules() if rule.endpoint == "api_upload_slide"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].rule, "/api/slides/upload")
        response = client.post("/api/slides/upload", data={"group": "grpBio"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "未收到檔案"})

    def test_direct_flask_app_registration_uses_canonical_request_actor(self):
        app = Flask(__name__ + "-direct")
        app.config.update(TESTING=True, SECRET_KEY="test")

        @app.before_request
        def bind_actor():
            g.teacher_user = {
                "username": "admin1",
                "role": "education_admin",
                "roles": ["education_admin"],
                "preferredGroup": "grpBio",
            }

        register_sync_upload_routes(app, runtime=_runtime(self.paths))
        response = app.test_client().post("/api/slides/upload", data={"group": "grpBio"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "未收到檔案"})

    def test_simple_r2_upload_preserves_response_and_repository_entry(self):
        progress = []
        runtime = _runtime(self.paths, progress=progress)
        client = self._register(runtime)
        with patch("teacher_app.materials.sync_upload.material_repository.get_material", return_value=None), patch(
            "teacher_app.materials.sync_upload.material_repository.insert_material"
        ) as insert:
            response = client.post(
                "/api/slides/upload",
                data={
                    "file": (io.BytesIO(b"hello material"), "notes.txt"),
                    "group": "grpBio",
                    "area": "internal",
                    "title": "Notes",
                    "progressId": "p1",
                    "materialId": "upload-abcdef123456",
                },
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_json()
        self.assertEqual(body["id"], "upload-abcdef123456")
        self.assertEqual(body["storageBackend"], "r2")
        self.assertEqual(body["viewerMode"], "download")
        self.assertEqual(body["viewUrl"], "/view/upload-abcdef123456")
        self.assertEqual(body["title"], "Notes")
        insert.assert_called_once()
        entry = insert.call_args.args[0]
        self.assertEqual(entry["storage_backend"], "r2")
        self.assertEqual(entry["group_key"], "grpBio")
        self.assertEqual(entry["training_area"], "internal")
        self.assertTrue(any(call[:3] == ("p1", 100, "教材建立完成") for call in progress if call and call[0] != "clear"))
        self.assertFalse((self.paths.upload_dir / "upload-abcdef123456").exists())

    def test_filename_is_normalized_and_macro_office_is_rejected(self):
        client = self._register(_runtime(self.paths))
        with patch("teacher_app.materials.sync_upload.material_repository.get_material", return_value=None), patch(
            "teacher_app.materials.sync_upload.material_repository.insert_material"
        ) as insert:
            normalized = client.post(
                "/api/slides/upload",
                data={"file": (io.BytesIO(b"hello"), "..\\folder/e\u0301vidence\x00.txt")},
                content_type="multipart/form-data",
            )
        self.assertEqual(normalized.status_code, 200, normalized.get_data(as_text=True))
        self.assertEqual(normalized.get_json()["filename"], "évidence.txt")
        self.assertEqual(insert.call_args.args[0]["filename"], "évidence.txt")

        rejected = client.post(
            "/api/slides/upload",
            data={"file": (io.BytesIO(b"macro"), "lesson.docm")},
            content_type="multipart/form-data",
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("巨集", rejected.get_json()["error"])

    def test_auto_classification_keeps_atlas_metadata(self):
        def classify(*args, **kwargs):
            return "atlas", "規則分類", "atlas keywords"

        client = self._register(_runtime(self.paths, classify=classify))
        with patch("teacher_app.materials.sync_upload.material_repository.get_material", return_value=None), patch(
            "teacher_app.materials.sync_upload.material_repository.insert_material"
        ):
            response = client.post(
                "/api/slides/upload",
                data={
                    "file": (io.BytesIO(b"atlas text"), "atlas.txt"),
                    "materialType": "auto",
                    "atlasCategory": "blood_cell",
                    "atlasMagnification": "100x",
                },
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_json()
        self.assertEqual(body["materialType"], "atlas")
        self.assertEqual(body["classificationMethod"], "規則分類")
        self.assertEqual(body["classificationReason"], "atlas keywords")
        self.assertEqual(body["atlasMeta"]["category"], "blood_cell")

    def test_backend_selection_failure_preserves_503(self):
        runtime = _runtime(self.paths)
        runtime.active_material_backend = lambda: (_ for _ in ()).throw(RuntimeError("storage unavailable"))
        client = self._register(runtime)
        response = client.post(
            "/api/slides/upload",
            data={"file": (io.BytesIO(b"x"), "notes.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"error": "storage unavailable"})

    def test_storage_failure_preserves_500_shape_and_rolls_back_prefix(self):
        deleted = []
        runtime = _runtime(self.paths, upload_error=RuntimeError("r2 failed"), deleted=deleted)
        client = self._register(runtime)
        with patch("teacher_app.materials.sync_upload.material_repository.get_material", return_value=None):
            response = client.post(
                "/api/slides/upload",
                data={
                    "file": (io.BytesIO(b"hello"), "notes.txt"),
                    "materialId": "upload-abcdef123456",
                },
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 500)
        body = response.get_json()
        self.assertEqual(body["stage"], "教材建立失敗")
        self.assertTrue(body["retryable"])
        self.assertIn("r2 failed", body["error"])
        self.assertIn(("r2", "materials/upload-abcdef123456/"), deleted)
        self.assertFalse((self.paths.upload_dir / "upload-abcdef123456").exists())


if __name__ == "__main__":
    unittest.main()
