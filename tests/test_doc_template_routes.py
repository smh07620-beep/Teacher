import io
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask, g

from teacher_app.config import StoragePaths
from teacher_app.materials import templates
from teacher_app.materials.template_runtime import DocumentTemplateRuntime
from teacher_app.materials.template_routes import register_doc_template_routes
from teacher_app.storage import DeleteOutcome, StorageDeletionError


def _docx_bytes() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
            "<Default Extension='xml' ContentType='application/xml'/></Types>",
        )
        archive.writestr(
            "word/document.xml",
            "<?xml version='1.0'?><w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
            "<w:body><w:p><w:r><w:t>" + ("範本" * 400) + "</w:t></w:r></w:p></w:body></w:document>",
        )
    return out.getvalue()


class _Base:
    GROUPS = {"grpBio": "1 生化組", "grpMicro": "2 鏡檢組"}
    MAX_DOC_TEMPLATE_MB = 20
    GDRIVE_FOLDER_ID = "drive-root"
    pymupdf = None

    def __init__(self, app):
        self.app = app
        self.admin_allowed = True
        self.delete_error = None

    def require_admin(self):
        raise AssertionError("legacy admin guard must not be used")

    def _current_user(self):
        if self.admin_allowed:
            return {"username": "root", "role": "system_admin"}
        return {"username": "student", "role": "student"}

    def active_material_backend(self):
        return "local"

    def _delete_storage_object(
        self,
        backend,
        key,
        *,
        local_payload=None,
        local_delete_object=None,
        best_effort=False,
    ):
        if self.delete_error is not None:
            if best_effort:
                return DeleteOutcome(backend, "object", False, self.delete_error)
            raise self.delete_error
        if backend == "local" and local_payload and local_delete_object:
            local_delete_object(local_payload)
        return DeleteOutcome(backend, "object", True)

    def mega_is_configured(self):
        return False

    def oci_is_configured(self):
        return False

    def gdrive_is_configured(self):
        return False

    def r2_is_configured(self):
        return False


class DocTemplateRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db_path = root / "templates.sqlite"
        self.paths = StoragePaths(
            base_dir=root,
            static_dir=root / "static",
            slides_dir=root / "static" / "slides",
            material_storage=root / "materials",
            upload_dir=root / "materials" / "ppt",
            question_images_dir=root / "materials" / "question_images",
            uploaded_slides_dir=root / "materials" / "slides",
            doc_templates_dir=root / "materials" / "doc_templates",
            pgy_assessment_templates_dir=root / "materials" / "pgy_assessment_templates",
            data_dir=root / "data",
            tmp_dir=root / "tmp",
            upload_progress_dir=root / "tmp" / "upload_progress",
            preview_cache_dir=root / "tmp" / "preview_cache",
        )
        for path in (
            self.paths.doc_templates_dir,
            self.paths.tmp_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

        def connect():
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.isolation_level = None
            return conn, "sqlite"

        self.db_patch = patch("teacher_app.common.db.get_connection", side_effect=connect)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        templates.init_schema()

        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.base = _Base(self.app)
        self.runtime = DocumentTemplateRuntime(self.paths)
        register_doc_template_routes(self.base, paths=self.paths, runtime=self.runtime)
        self.client = self.app.test_client()

    def test_exact_endpoints_and_public_list(self):
        expected = {
            "api_list_doc_templates",
            "api_upload_doc_template",
            "api_download_doc_template",
            "api_delete_doc_template",
        }
        self.assertTrue(expected.issubset(self.app.view_functions))
        response = self.client.get("/api/doc-templates")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(
            [item["group"] for item in body],
            ["grpBio", "grpMicro", "grpSero", "grpBB", "grpBact", "grpHema", "grpNew", "grpPgyDocs"],
        )
        self.assertFalse(body[0]["exists"])

    def test_local_upload_download_and_delete(self):
        response = self.client.post(
            "/api/doc-templates/grpBio",
            data={"file": (io.BytesIO(_docx_bytes()), "my-template.docx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["storageBackend"], "local")
        row = templates.get_template("grpBio")
        self.assertEqual(row["filename"], "my-template.docx")
        self.assertTrue((self.paths.doc_templates_dir / "grpBio.docx").exists())

        downloaded = self.client.get("/api/doc-templates/grpBio/download")
        self.assertEqual(downloaded.status_code, 200)
        payload = downloaded.data
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            self.assertIn("[Content_Types].xml", archive.namelist())
            self.assertIn("word/document.xml", archive.namelist())
        downloaded.close()

        deleted = self.client.delete("/api/doc-templates/grpBio")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.get_json(), {"ok": True})
        self.assertIsNone(templates.get_template("grpBio"))
        self.assertFalse((self.paths.doc_templates_dir / "grpBio.docx").exists())

    def test_validation_and_admin_contract(self):
        invalid_group = self.client.post(
            "/api/doc-templates/nope",
            data={"file": (io.BytesIO(_docx_bytes()), "x.docx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(invalid_group.status_code, 400)
        bad_ext = self.client.post(
            "/api/doc-templates/grpBio",
            data={"file": (io.BytesIO(b"not docx"), "x.pdf")},
            content_type="multipart/form-data",
        )
        self.assertEqual(bad_ext.status_code, 400)
        self.base.admin_allowed = False
        denied = self.client.delete("/api/doc-templates/grpBio")
        self.assertEqual(denied.status_code, 403)

    def test_strict_delete_failure_keeps_metadata(self):
        templates.save_template("grpBio", "x.docx", "grpBio.docx", "r2", "doc/key")
        failure = StorageDeletionError("r2", "object", RuntimeError("delete failed"))
        with patch.object(self.runtime, "delete", side_effect=failure):
            response = self.client.delete("/api/doc-templates/grpBio")
        self.assertEqual(response.status_code, 502)
        self.assertIn("Word 範本刪除失敗", response.get_json()["error"])
        self.assertIsNotNone(templates.get_template("grpBio"))

    def test_replacement_cleanup_is_best_effort(self):
        templates.save_template("grpBio", "old.docx", "grpBio.docx", "r2", "old/key")
        failed_cleanup = DeleteOutcome("r2", "object", False, RuntimeError("cleanup failed"))
        with patch.object(self.runtime, "delete", return_value=failed_cleanup) as delete:
            response = self.client.post(
                "/api/doc-templates/grpBio",
                data={"file": (io.BytesIO(_docx_bytes()), "new.docx")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        delete.assert_called_once()
        self.assertTrue(delete.call_args.kwargs["best_effort"])
        self.assertEqual(templates.get_template("grpBio")["filename"], "new.docx")

    def test_remote_download_configuration_errors_preserve_503_shapes(self):
        messages = {
            "mega": "MEGA 尚未設定完成，無法讀取 Word 範本",
            "oci": "Oracle Object Storage 尚未設定完成，無法讀取 Word 範本",
            "gdrive": "Google Drive 尚未設定完成，無法讀取 Word 範本",
            "r2": "Cloudflare R2 尚未設定完成，無法讀取 Word 範本",
        }
        for backend, message in messages.items():
            with self.subTest(backend=backend):
                templates.save_template("grpBio", "x.docx", "grpBio.docx", backend, "remote/key")
                with patch.object(self.runtime, "configured", return_value=False):
                    response = self.client.get("/api/doc-templates/grpBio/download")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.get_json(), {"error": message})

    def test_direct_flask_registration_uses_request_bound_actor(self):
        app = Flask("direct-doc-template")
        app.config.update(TESTING=True, SECRET_KEY="test")

        @app.before_request
        def bind_actor():
            g.teacher_user = {"username": "root", "role": "system_admin"}

        runtime = DocumentTemplateRuntime(self.paths)
        register_doc_template_routes(app, paths=self.paths, runtime=runtime)
        response = app.test_client().delete("/api/doc-templates/grpMicro")
        self.assertEqual(response.status_code, 200)

    def test_r2_store_requires_explicit_ledger_callback(self):
        class R2Storage:
            free_only = True

            @staticmethod
            def active_backend():
                return "r2"

        source = self.paths.tmp_dir / "r2.docx"
        source.write_bytes(_docx_bytes())
        runtime = DocumentTemplateRuntime(self.paths, storage_adapter=R2Storage())
        with self.assertRaisesRegex(RuntimeError, "ledger callback"):
            runtime.store(source, "grpBio", "grpBio.docx")

    def test_mega_gdrive_oci_and_r2_store_use_canonical_provider_owners(self):
        source = self.paths.tmp_dir / "remote.docx"
        source.write_bytes(_docx_bytes())

        class MegaStorage:
            free_only = True

            @staticmethod
            def active_backend():
                return "mega"

            @staticmethod
            def _mega_free_guard(_size):
                return None

            @staticmethod
            def _mega_root():
                return "/root"

            @staticmethod
            def _mega_remote_join(*parts):
                return "/" + "/".join(str(item).strip("/") for item in parts)

            @staticmethod
            def _mega_ensure_dir(path):
                return path

            @staticmethod
            def _mega_upload_file(_path, folder, name):
                return f"{folder}/{name}"

        mega = DocumentTemplateRuntime(self.paths, storage_adapter=MegaStorage())
        backend, key = mega.store(source, "grpBio", "grpBio.docx")
        self.assertEqual(backend, "mega")
        self.assertTrue(key.startswith("/root/doc-templates/word-template-grpBio-"))

        class CloudStorage:
            free_only = False

            def __init__(self, backend):
                self.backend = backend

            def active_backend(self):
                return self.backend

        service = Mock()
        files = service.files.return_value
        files.create.return_value.execute.return_value = {"id": "drive-file"}
        with patch("teacher_app.materials.template_runtime.providers.gdrive_service", return_value=service), patch(
            "teacher_app.materials.template_runtime.providers.gdrive_media_file_upload",
            return_value=object(),
        ), patch("teacher_app.materials.template_runtime.providers.GDRIVE_FOLDER_ID", "drive-root"):
            runtime = DocumentTemplateRuntime(self.paths, storage_adapter=CloudStorage("gdrive"))
            self.assertEqual(runtime.store(source, "grpBio", "grpBio.docx"), ("gdrive", "drive-file"))
        create_body = files.create.call_args.kwargs["body"]
        self.assertEqual(create_body["parents"], ["drive-root"])
        self.assertEqual(create_body["appProperties"]["smh_group"], "grpBio")

        for backend, client_name, bucket_name in (
            ("oci", "oci_client", "OCI_BUCKET_NAME"),
            ("r2", "r2_client", "R2_BUCKET_NAME"),
        ):
            with self.subTest(backend=backend):
                client = Mock()
                recorded = []
                runtime = DocumentTemplateRuntime(
                    self.paths,
                    storage_adapter=CloudStorage(backend),
                    r2_record_object=lambda key, size: recorded.append((key, size)),
                )
                with patch(
                    f"teacher_app.materials.template_runtime.providers.{client_name}",
                    return_value=client,
                ), patch(
                    f"teacher_app.materials.template_runtime.providers.{bucket_name}",
                    f"{backend}-bucket",
                ):
                    stored_backend, stored_key = runtime.store(source, "grpBio", "grpBio.docx")
                self.assertEqual(stored_backend, backend)
                self.assertTrue(stored_key.startswith("doc_templates/grpBio/"))
                self.assertEqual(client.upload_file.call_args.args[1], f"{backend}-bucket")
                if backend == "r2":
                    self.assertEqual(recorded, [(stored_key, source.stat().st_size)])


if __name__ == "__main__":
    unittest.main()
