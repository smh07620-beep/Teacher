import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask, g, jsonify

from teacher_app.config import StoragePaths
from teacher_app.storage import admin_service
from teacher_app.storage.admin_routes import register_storage_admin_routes


class _Base:
    def __init__(self, app):
        self.app = app

    def require_admin(self):
        raise AssertionError("legacy admin guard must not be used")

    def _current_user(self):
        return {"username": "root", "role": "system_admin"}


def _paths(root: Path) -> StoragePaths:
    storage = root / "storage"
    paths = StoragePaths(
        base_dir=root,
        static_dir=root / "static",
        slides_dir=root / "static" / "slides",
        material_storage=storage,
        upload_dir=storage / "ppt",
        question_images_dir=storage / "question_images",
        uploaded_slides_dir=storage / "slides",
        doc_templates_dir=storage / "doc_templates",
        pgy_assessment_templates_dir=storage / "pgy_assessment_templates",
        data_dir=root / "data",
        tmp_dir=root / "tmp",
        upload_progress_dir=root / "tmp" / "upload_progress",
        preview_cache_dir=root / "tmp" / "preview_cache",
    )
    for path in (paths.upload_dir, paths.uploaded_slides_dir, paths.tmp_dir):
        path.mkdir(parents=True, exist_ok=True)
    return paths


def _runtime(paths: StoragePaths, **overrides):
    values = dict(
        paths_provider=lambda: paths,
        active_material_backend=lambda: "local",
        fallback_backend_ready=lambda: "",
        gdrive_is_configured=lambda: False,
        gdrive_check=lambda: {},
        mega_is_configured=lambda: False,
        mega_storage_space=lambda: {"used": 0, "total": 0},
        oci_is_configured=lambda: False,
        oci_bucket_usage_bytes=lambda: 0,
        r2_is_configured=lambda: False,
        upload_material_tree_to_gdrive=lambda *args, **kwargs: ("key", "slides", {}),
        upload_material_tree_to_r2=lambda *args, **kwargs: ("key", "slides"),
        r2_delete_prefix=lambda prefix: None,
        configured_mode="auto",
        fallback_backend="",
        failover_on_full=False,
        free_only_mode=True,
        mega_free_limit_gb=18.0,
        oci_free_limit_gb=19.5,
        oci_presign_seconds=1800,
        r2_presign_seconds=3600,
        cache_seconds=30,
        status_cache={"at": 0.0, "data": None},
        status_lock=threading.RLock(),
    )
    values.update(overrides)
    return admin_service.StorageAdminRuntime(**values)


class StorageAdminRoutesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = _paths(Path(self.temp.name))

    def test_registrar_replaces_legacy_endpoints_without_duplicate_rules(self):
        app = Flask(__name__)
        base = _Base(app)
        app.add_url_rule("/api/storage-status", "api_storage_status", lambda: jsonify({"legacy": True}), methods=["GET"])
        app.add_url_rule("/api/storage/migrate-to-gdrive", "api_migrate_materials_to_gdrive", lambda: jsonify({"legacy": True}), methods=["POST"])
        app.add_url_rule("/api/storage/migrate-to-r2", "api_migrate_materials_to_r2", lambda: jsonify({"legacy": True}), methods=["POST"])
        runtime = _runtime(self.paths)
        with patch("teacher_app.storage.admin_service.material_repository.list_uploaded_materials", return_value=[]):
            register_storage_admin_routes(base, runtime=runtime)
            response = app.test_client().get("/api/storage-status")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("legacy", response.get_json())
        self.assertEqual(
            [rule.endpoint for rule in app.url_map.iter_rules() if rule.rule.startswith("/api/storage")],
            ["api_storage_status", "api_migrate_materials_to_gdrive", "api_migrate_materials_to_r2"],
        )

    def test_direct_flask_registration_uses_request_bound_actor(self):
        app = Flask("direct-storage-admin")

        @app.before_request
        def bind_actor():
            g.teacher_user = {"username": "root", "role": "system_admin"}

        register_storage_admin_routes(app, runtime=_runtime(self.paths))
        with patch("teacher_app.storage.admin_service.material_repository.list_uploaded_materials", return_value=[]):
            response = app.test_client().get("/api/storage-status")
        self.assertEqual(response.status_code, 200)

    def test_storage_status_preserves_payload_and_refresh_cache_contract(self):
        calls = {"active": 0}

        def active():
            calls["active"] += 1
            return "gdrive"

        runtime = _runtime(
            self.paths,
            active_material_backend=active,
            fallback_backend_ready=lambda: "gdrive",
            gdrive_is_configured=lambda: True,
            gdrive_check=lambda: {"name": "Teaching"},
            configured_mode="auto",
            fallback_backend="gdrive",
            failover_on_full=True,
        )
        materials = [
            {"storageBackend": "gdrive"},
            {"storageBackend": "r2"},
            {"storageBackend": "local"},
        ]
        with patch("teacher_app.storage.admin_service.material_repository.list_uploaded_materials", return_value=materials):
            first = admin_service.storage_status(runtime)
            second = admin_service.storage_status(runtime)
            refreshed = admin_service.storage_status(runtime, force=True)
        self.assertEqual(first, second)
        self.assertEqual(calls["active"], 2)
        self.assertEqual(refreshed["configuredMode"], "auto")
        self.assertEqual(refreshed["activeBackend"], "gdrive")
        self.assertEqual(refreshed["fallbackBackend"], "gdrive")
        self.assertTrue(refreshed["failoverOnFull"])
        self.assertTrue(refreshed["fallbackReady"])
        self.assertTrue(refreshed["gdriveConnected"])
        self.assertEqual(refreshed["gdriveFolderName"], "Teaching")
        self.assertEqual(refreshed["materials"], {"mega": 0, "oci": 0, "gdrive": 1, "r2": 1, "local": 1})
        self.assertEqual(refreshed["error"], "")
        self.assertEqual(refreshed["cachedSeconds"], 30)

    def test_gdrive_configuration_and_check_errors_preserve_400_json(self):
        app = Flask(__name__)
        base = _Base(app)
        register_storage_admin_routes(base, runtime=_runtime(self.paths))
        response = app.test_client().post("/api/storage/migrate-to-gdrive")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {
            "error": "Google Drive 尚未設定完成，無法搬移。請先設定 OAuth refresh token 與 GDRIVE_FOLDER_ID。"
        })

        app2 = Flask(__name__ + "2")
        base2 = _Base(app2)
        runtime = _runtime(
            self.paths,
            gdrive_is_configured=lambda: True,
            gdrive_check=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        register_storage_admin_routes(base2, runtime=runtime)
        response = app2.test_client().post("/api/storage/migrate-to-gdrive")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Google Drive 連線/資料夾檢查失敗：boom"})

    def test_local_to_gdrive_updates_repository_then_cleans_local_tree(self):
        entry = {
            "id": "m1",
            "title": "One",
            "storageBackend": "local",
            "storageFilename": "source.pdf",
            "folder": "m1",
            "pageCount": 2,
            "filename": "original.pdf",
        }
        source_dir = self.paths.upload_dir / "m1"
        slides_dir = self.paths.uploaded_slides_dir / "m1"
        source_dir.mkdir(parents=True)
        slides_dir.mkdir(parents=True)
        source = source_dir / "source.pdf"
        source.write_bytes(b"pdf")
        seen = {}

        def upload(material_id, source_path, slides_path, page_count, *, original_name):
            seen.update({
                "id": material_id,
                "source": source_path,
                "slides": slides_path,
                "pageCount": page_count,
                "original": original_name,
            })
            return "file-1", "slides-1", {"slideFormat": "png"}

        runtime = _runtime(
            self.paths,
            gdrive_is_configured=lambda: True,
            gdrive_check=lambda: {"name": "Teaching"},
            upload_material_tree_to_gdrive=upload,
        )
        with patch("teacher_app.storage.admin_service.material_repository.list_uploaded_materials", return_value=[entry]), patch(
            "teacher_app.storage.admin_service.material_repository.update_material_storage"
        ) as update:
            payload, status = admin_service.migrate_materials_to_gdrive(runtime)
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True, "migrated": 1, "skipped": [], "failed": []})
        self.assertEqual(seen["source"], source)
        self.assertEqual(seen["slides"], slides_dir)
        update.assert_called_once_with(
            "m1",
            backend="gdrive",
            storage_key="file-1",
            slides_prefix="slides-1",
            storage_meta_json='{"slideFormat": "png"}',
        )
        self.assertFalse(source_dir.exists())
        self.assertFalse(slides_dir.exists())

    def test_r2_to_gdrive_uses_temp_tree_deletes_old_prefix_and_always_cleans_temp(self):
        entry = {
            "id": "r2-1",
            "title": "Remote",
            "storageBackend": "r2",
            "storageFilename": "source.pdf",
            "folder": "r2-1",
            "pageCount": 1,
            "filename": "original.pdf",
        }
        deleted = []
        observed_temp_roots = []

        def download(item, source, slides):
            observed_temp_roots.append(source.parents[1])
            source.write_bytes(b"pdf")
            (slides / "slide-01.png").write_bytes(b"png")

        runtime = _runtime(
            self.paths,
            gdrive_is_configured=lambda: True,
            gdrive_check=lambda: {"name": "Teaching"},
            r2_is_configured=lambda: True,
            download_material_from_r2=download,
            upload_material_tree_to_gdrive=lambda *args, **kwargs: (
                "drive-source", "drive-slides", {"slideFormat": "png"}
            ),
            r2_delete_prefix=deleted.append,
        )
        with patch("teacher_app.storage.admin_service.material_repository.list_uploaded_materials", return_value=[entry]), patch(
            "teacher_app.storage.admin_service.material_repository.update_material_storage"
        ) as update:
            payload, status = admin_service.migrate_materials_to_gdrive(runtime)
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True, "migrated": 1, "skipped": [], "failed": []})
        self.assertEqual(deleted, ["materials/r2-1/"])
        update.assert_called_once()
        self.assertEqual(len(observed_temp_roots), 1)
        self.assertFalse(observed_temp_roots[0].exists())

    def test_r2_migration_preserves_skip_cleanup_and_failure_rollback(self):
        local = {
            "id": "local-1", "title": "Local", "storageBackend": "local",
            "storageFilename": "source.pdf", "folder": "local-1", "pageCount": 1,
        }
        drive = {"id": "drive-1", "title": "Drive", "storageBackend": "gdrive"}
        failed = {
            "id": "bad-1", "title": "Bad", "storageBackend": "local",
            "storageFilename": "source.pdf", "folder": "bad-1", "pageCount": 0,
        }
        for entry in (local, failed):
            source_dir = self.paths.upload_dir / entry["id"]
            slides_dir = self.paths.uploaded_slides_dir / entry["folder"]
            source_dir.mkdir(parents=True)
            slides_dir.mkdir(parents=True)
            (source_dir / "source.pdf").write_bytes(b"pdf")

        deleted = []

        def upload(material_id, source, slides, page_count):
            if material_id == "bad-1":
                raise RuntimeError("upload failed")
            return f"materials/{material_id}/source.pdf", f"materials/{material_id}/slides"

        runtime = _runtime(
            self.paths,
            r2_is_configured=lambda: True,
            upload_material_tree_to_r2=upload,
            r2_delete_prefix=deleted.append,
        )
        with patch("teacher_app.storage.admin_service.material_repository.list_uploaded_materials", return_value=[local, drive, failed]), patch(
            "teacher_app.storage.admin_service.material_repository.update_material_storage"
        ) as update:
            payload, status = admin_service.migrate_materials_to_r2(runtime)
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["migrated"], 1)
        self.assertEqual(payload["skipped"], [{
            "id": "drive-1", "title": "Drive",
            "reason": "目前已在 Google Drive；R2 搬移工具僅處理本機教材",
        }])
        self.assertEqual(payload["failed"], [{"id": "bad-1", "title": "Bad", "reason": "upload failed"}])
        self.assertIn("materials/bad-1/", deleted)
        update.assert_called_once_with(
            "local-1",
            backend="r2",
            storage_key="materials/local-1/source.pdf",
            slides_prefix="materials/local-1/slides",
        )
        self.assertFalse((self.paths.upload_dir / "local-1").exists())
        self.assertTrue((self.paths.upload_dir / "bad-1").exists())

    def test_canonical_runtime_r2_tree_uses_explicit_accounting_callbacks(self):
        class Storage:
            requested_backend = "auto"
            free_only = True

            @staticmethod
            def active_backend():
                return "local"

            @staticmethod
            def mega_is_configured():
                return False

            @staticmethod
            def _mega_storage_space():
                return {"used": 0, "total": 0}

            @staticmethod
            def upload_material_tree_to_gdrive(*args, **kwargs):
                return "drive", "slides", {}

            @staticmethod
            def _content_type(_path):
                return "application/octet-stream"

            @staticmethod
            def _slide_local_path(directory, page_no):
                return Path(directory) / f"slide-{page_no:02d}.png"

        source = self.paths.upload_dir / "source.pdf"
        slides = self.paths.uploaded_slides_dir / "runtime-r2"
        source.write_bytes(b"source")
        slides.mkdir(parents=True)
        (slides / "slide-01.png").write_bytes(b"slide")
        client = Mock()
        recorded = []
        deleted = []
        with patch("teacher_app.storage.admin_service.providers.r2_client", return_value=client), patch(
            "teacher_app.storage.admin_service.providers.R2_BUCKET_NAME", "bucket"
        ), patch("teacher_app.storage.admin_service.material_storage.delete_prefix") as delete_prefix:
            runtime = admin_service.build_canonical_runtime(
                paths_provider=lambda: self.paths,
                storage_adapter=Storage(),
                r2_record_object=lambda key, size: recorded.append((key, size)),
                r2_record_deleted=deleted.append,
            )
            key, prefix = runtime.upload_material_tree_to_r2("m1", source, slides, 1)
            runtime.r2_delete_prefix("materials/m1/")

        self.assertEqual(key, "materials/m1/source.pdf")
        self.assertEqual(prefix, "materials/m1/slides")
        self.assertEqual([item[0] for item in recorded], [key, "materials/m1/slides/slide-01.png"])
        self.assertEqual(client.upload_file.call_count, 2)
        on_deleted = delete_prefix.call_args.kwargs["on_deleted"]
        on_deleted("materials/m1/source.pdf")
        self.assertEqual(deleted, ["materials/m1/source.pdf"])

    def test_canonical_runtime_downloads_r2_source_and_slides_for_gdrive_migration(self):
        class Storage:
            requested_backend = "auto"
            free_only = True

            @staticmethod
            def active_backend():
                return "local"

            @staticmethod
            def mega_is_configured():
                return False

            @staticmethod
            def _mega_storage_space():
                return {"used": 0, "total": 0}

            @staticmethod
            def upload_material_tree_to_gdrive(*args, **kwargs):
                return "drive", "slides", {}

        client = Mock()

        def download(_bucket, key, target):
            Path(target).write_bytes(key.encode("utf-8"))

        client.download_file.side_effect = download
        client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "materials/m1/slides/slide-01.png"},
                {"Key": "materials/m1/slides/slide-02.webp"},
            ],
            "IsTruncated": False,
        }
        source = self.paths.tmp_dir / "download" / "source.pdf"
        slides = self.paths.tmp_dir / "download" / "slides"
        with patch("teacher_app.storage.admin_service.providers.r2_client", return_value=client), patch(
            "teacher_app.storage.admin_service.providers.R2_BUCKET_NAME", "bucket"
        ):
            runtime = admin_service.build_canonical_runtime(
                paths_provider=lambda: self.paths,
                storage_adapter=Storage(),
            )
            runtime.download_material_from_r2(
                {
                    "storageKey": "materials/m1/source.pdf",
                    "slidesPrefix": "materials/m1/slides",
                },
                source,
                slides,
            )

        self.assertTrue(source.is_file())
        self.assertTrue((slides / "slide-01.png").is_file())
        self.assertTrue((slides / "slide-02.webp").is_file())

    def test_canonical_runtime_r2_upload_fails_closed_without_ledger_owner(self):
        class Storage:
            requested_backend = "auto"
            free_only = True

            @staticmethod
            def active_backend():
                return "local"

            @staticmethod
            def mega_is_configured():
                return False

            @staticmethod
            def _mega_storage_space():
                return {"used": 0, "total": 0}

            @staticmethod
            def upload_material_tree_to_gdrive(*args, **kwargs):
                return "drive", "slides", {}

            @staticmethod
            def _content_type(_path):
                return "application/octet-stream"

            @staticmethod
            def _slide_local_path(directory, page_no):
                return Path(directory) / f"slide-{page_no:02d}.png"

        source = self.paths.upload_dir / "no-ledger.pdf"
        source.write_bytes(b"source")
        runtime = admin_service.build_canonical_runtime(
            paths_provider=lambda: self.paths,
            storage_adapter=Storage(),
        )
        with self.assertRaisesRegex(RuntimeError, "ledger callback"):
            runtime.upload_material_tree_to_r2("m1", source, self.paths.uploaded_slides_dir, 0)


if __name__ == "__main__":
    unittest.main()
