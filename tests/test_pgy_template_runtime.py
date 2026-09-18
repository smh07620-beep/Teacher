import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from flask import Flask, g

from teacher_app.pgy import assessment_routes
from teacher_app.pgy.template_runtime import PgyTemplateRuntime
from teacher_app.storage import providers
from teacher_app.storage.service import StorageDeletionError


class FakeStorageAdapter:
    def __init__(self, backend="local"):
        self.backend = backend
        self.free_only = False
        self.mega_uploads = []

    def active_backend(self):
        return self.backend

    def mega_is_configured(self):
        return True

    def _mega_free_guard(self, _size):
        return None

    def _mega_root(self):
        return "/teacher-root"

    @staticmethod
    def _mega_remote_join(*parts):
        return "/" + "/".join(str(part).strip("/") for part in parts if str(part).strip("/"))

    def _mega_ensure_dir(self, path):
        return path

    def _mega_upload_file(self, local_path, folder, remote_name):
        self.mega_uploads.append((Path(local_path), folder, remote_name))
        return self._mega_remote_join(folder, remote_name)

    def _mega_run(self, *_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class FakeObjectClient:
    def __init__(self, url="https://example.invalid/object"):
        self.url = url
        self.uploads = []
        self.presigns = []

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        self.uploads.append((filename, bucket, key, ExtraArgs or {}))

    def generate_presigned_url(self, operation, Params=None, ExpiresIn=None):
        self.presigns.append((operation, Params or {}, ExpiresIn))
        return self.url


class FakeUpstream:
    def __init__(self, status_code=206):
        self.status_code = status_code
        self.headers = {
            "Content-Type": "application/pdf",
            "Content-Length": "3",
            "Content-Range": "bytes 0-2/3",
            "Accept-Ranges": "bytes",
        }
        self.text = "upstream error"
        self.closed = False

    def iter_content(self, chunk_size):
        self.chunk_size = chunk_size
        yield b"pdf"

    def close(self):
        self.closed = True


class FakeAuthorizedSession:
    def __init__(self, upstream):
        self.upstream = upstream
        self.calls = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.upstream

    def close(self):
        self.closed = True


class PgyTemplateRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.paths = SimpleNamespace(
            tmp_dir=root / "tmp",
            pgy_assessment_templates_dir=root / "pgy-templates",
        )
        self.paths.tmp_dir.mkdir(parents=True)
        self.paths.pgy_assessment_templates_dir.mkdir(parents=True)

    def tearDown(self):
        self.tempdir.cleanup()

    def _valid_docx(self):
        path = self.paths.tmp_dir / "template.docx"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(
                "[Content_Types].xml",
                "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'></Types>",
            )
            archive.writestr(
                "word/document.xml",
                "<?xml version='1.0'?><w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body/></w:document>",
            )
            archive.writestr("word/media/filler.bin", b"x" * 4096)
        return path

    def test_local_validate_store_send_and_strict_delete(self):
        runtime = PgyTemplateRuntime(
            self.paths,
            storage_adapter=FakeStorageAdapter("local"),
        )
        source = self._valid_docx()
        validation = runtime.validate(source, ".docx")
        self.assertEqual(validation["kind"], "docx")

        backend, key = runtime.store(source, "dops", "DOPS.docx")
        self.assertEqual(backend, "local")
        stored = Path(key)
        self.assertTrue(stored.is_file())
        self.assertEqual(stored.parent, self.paths.pgy_assessment_templates_dir)

        app = Flask(__name__)
        with app.test_request_context("/api/pgy-assessment-templates/dops/download"):
            response = runtime.send(
                {"storage_backend": "local", "storage_key": key, "filename": "DOPS.docx"},
                inline=True,
            )
            self.assertEqual(response.status_code, 200)
            response.close()

        outcome = runtime.delete(
            {"storage_backend": "local", "storage_key": key},
            best_effort=False,
        )
        self.assertTrue(outcome.deleted)
        self.assertFalse(stored.exists())

    def test_mega_store_uses_shared_canonical_storage_adapter(self):
        adapter = FakeStorageAdapter("mega")
        runtime = PgyTemplateRuntime(self.paths, storage_adapter=adapter)
        source = self._valid_docx()

        backend, key = runtime.store(source, "mini_cex", "MINI-CEX.docx")

        self.assertEqual(backend, "mega")
        self.assertTrue(key.startswith("/teacher-root/pgy-assessment-templates/mini_cex-"))
        self.assertEqual(len(adapter.mega_uploads), 1)

    def test_oci_and_r2_store_and_send_use_provider_owned_clients(self):
        app = Flask(__name__)
        source = self._valid_docx()
        cases = (
            ("oci", "OCI_BUCKET_NAME", "oci_client", "OCI_PRESIGN_SECONDS"),
            ("r2", "R2_BUCKET_NAME", "r2_client", "R2_PRESIGN_SECONDS"),
        )
        for backend, bucket_name, client_name, expires_name in cases:
            with self.subTest(backend=backend):
                adapter = FakeStorageAdapter(backend)
                runtime = PgyTemplateRuntime(self.paths, storage_adapter=adapter)
                client = FakeObjectClient(f"https://example.invalid/{backend}")
                with mock.patch.object(providers, bucket_name, f"{backend}-bucket"), mock.patch.object(
                    providers, client_name, return_value=client
                ):
                    stored_backend, key = runtime.store(source, "cbd", "CBD.docx")
                    self.assertEqual(stored_backend, backend)
                    self.assertTrue(key.startswith("pgy_assessment_templates/cbd/"))
                    self.assertEqual(client.uploads[0][1], f"{backend}-bucket")

                    with app.test_request_context("/download"):
                        response = runtime.send(
                            {
                                "storage_backend": backend,
                                "storage_key": key,
                                "filename": "CBD.docx",
                            }
                        )
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.location, f"https://example.invalid/{backend}")
                    self.assertEqual(
                        client.presigns[-1][2],
                        getattr(providers, expires_name),
                    )

    def test_gdrive_store_reuses_named_template_folder(self):
        runtime = PgyTemplateRuntime(
            self.paths,
            storage_adapter=FakeStorageAdapter("gdrive"),
        )
        source = self._valid_docx()
        with mock.patch.object(runtime, "_gdrive_find_file_in_folder", return_value="folder-1") as find, mock.patch.object(
            runtime, "_gdrive_create_folder"
        ) as create, mock.patch.object(
            runtime, "_gdrive_upload_file", return_value="file-1"
        ) as upload, mock.patch.object(
            providers, "GDRIVE_FOLDER_ID", "root-folder"
        ):
            backend, key = runtime.store(source, "qc", "QC.docx")

        self.assertEqual((backend, key), ("gdrive", "file-1"))
        find.assert_called_once_with("root-folder", "pgy-assessment-templates")
        create.assert_not_called()
        self.assertEqual(upload.call_args.args[2], "folder-1")

    def test_gdrive_send_preserves_range_and_inline_headers(self):
        runtime = PgyTemplateRuntime(
            self.paths,
            storage_adapter=FakeStorageAdapter("gdrive"),
        )
        app = Flask(__name__)
        upstream = FakeUpstream()
        session = FakeAuthorizedSession(upstream)
        with mock.patch.object(providers, "gdrive_authorized_session", return_value=session), app.test_request_context(
            "/download",
            headers={"Range": "bytes=0-2"},
        ):
            response = runtime.send(
                {
                    "storage_backend": "gdrive",
                    "storage_key": "file-1",
                    "filename": "評量.pdf",
                },
                inline=True,
            )
            self.assertEqual(response.status_code, 206)
            self.assertIn("inline", response.headers["Content-Disposition"])
            self.assertIn("filename*=UTF-8''", response.headers["Content-Disposition"])
            self.assertEqual(session.calls[0][1]["headers"]["Range"], "bytes=0-2")
            response.close()
        self.assertTrue(upstream.closed)
        self.assertTrue(session.closed)

    def test_mega_send_uses_temporary_file_and_cleans_it_on_close(self):
        runtime = PgyTemplateRuntime(
            self.paths,
            storage_adapter=FakeStorageAdapter("mega"),
        )
        app = Flask(__name__)

        def fake_download(_key, target):
            Path(target).write_bytes(b"template")
            return Path(target)

        with mock.patch.object(runtime, "_mega_download", side_effect=fake_download), app.test_request_context(
            "/download"
        ):
            response = runtime.send(
                {
                    "storage_backend": "mega",
                    "storage_key": "/remote/template.docx",
                    "filename": "template.docx",
                }
            )
            self.assertEqual(response.status_code, 200)
            response.close()

        self.assertEqual(list(self.paths.tmp_dir.glob("pgy-template-read-*")), [])

    def test_strict_remote_delete_uses_provider_delete_owner(self):
        runtime = PgyTemplateRuntime(
            self.paths,
            storage_adapter=FakeStorageAdapter("r2"),
        )
        with mock.patch.object(providers, "r2_is_configured", return_value=True), mock.patch.object(
            providers, "r2_delete_object"
        ) as delete:
            outcome = runtime.delete(
                {"storage_backend": "r2", "storage_key": "pgy/template.docx"},
                best_effort=False,
            )
        self.assertTrue(outcome.deleted)
        delete.assert_called_once_with("pgy/template.docx")


class FakeTemplateRuntime:
    def __init__(self):
        self.validated = []
        self.stored = []
        self.deleted = []

    def validate(self, path, ext):
        self.validated.append((Path(path), ext))
        return {"kind": ext.lstrip("."), "sizeBytes": Path(path).stat().st_size}

    def store(self, path, template_type, filename):
        self.stored.append((Path(path), template_type, filename))
        return "local", f"/stored/{template_type}{Path(filename).suffix}"

    def delete(self, row, *, best_effort=True):
        self.deleted.append((dict(row), best_effort))
        return SimpleNamespace(deleted=True)

    def send(self, row, *, inline=True):
        return {"row": dict(row), "inline": inline}


class PgyAssessmentRouteOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.paths = SimpleNamespace(
            tmp_dir=root / "tmp",
            pgy_assessment_templates_dir=root / "pgy-templates",
        )
        self.paths.tmp_dir.mkdir(parents=True)
        self.paths.pgy_assessment_templates_dir.mkdir(parents=True)
        self.app = Flask(__name__)
        self.app.secret_key = "test"
        self.actor = {
            "username": "admin",
            "role": "system_admin",
            "roles": ["system_admin"],
            "preferredGroup": "grpBio",
        }

        @self.app.before_request
        def bind_actor():
            g.teacher_user = self.actor

        self.owner = SimpleNamespace(app=self.app)
        self.runtime = FakeTemplateRuntime()
        assessment_routes.register_pgy_assessment_routes(
            self.owner,
            paths=self.paths,
            template_runtime=self.runtime,
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_upload_needs_only_owner_app_and_canonical_runtime(self):
        with mock.patch.object(assessment_routes.assessments, "get_template", return_value=None), mock.patch.object(
            assessment_routes.assessments, "save_template"
        ) as save:
            response = self.client.post(
                "/api/pgy-assessment-templates/dops",
                data={"file": (io.BytesIO(b"template"), "DOPS.docx")},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["storageBackend"], "local")
        self.assertEqual(len(self.runtime.validated), 1)
        self.assertEqual(len(self.runtime.stored), 1)
        save.assert_called_once()

    def test_delete_storage_failure_keeps_metadata_row(self):
        failure = StorageDeletionError("oci", "object", RuntimeError("delete failed"))
        row = {"storage_backend": "oci", "storage_key": "pgy/key", "filename": "EPA.pdf"}
        self.runtime.delete = mock.Mock(side_effect=failure)
        with mock.patch.object(assessment_routes.assessments, "get_template", return_value=row), mock.patch.object(
            assessment_routes.assessments, "delete_template"
        ) as delete_row:
            response = self.client.delete("/api/pgy-assessment-templates/epa")

        self.assertEqual(response.status_code, 502)
        self.assertIn("評量範本刪除失敗：delete failed", response.get_json()["error"])
        delete_row.assert_not_called()

    def test_list_assessments_admin_override_uses_canonical_admin_key(self):
        self.actor = None
        with mock.patch.object(assessment_routes, "admin_key", return_value="secret"), mock.patch.object(
            assessment_routes.assessments, "list_assessments", return_value=[]
        ) as listing:
            response = self.client.get(
                "/api/pgy-assessments",
                headers={"X-Admin-Key": "secret"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(listing.call_args.kwargs["admin_override"])
        self.assertIsNone(listing.call_args.args[0])

    def test_route_source_has_no_legacy_template_or_base_dependencies(self):
        source = Path(assessment_routes.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "base._current_user",
            "base.require_admin",
            "base.require_roles",
            "base.ADMIN_KEY",
            "base._validate_template_file",
            "base._store_pgy_template",
            "base._send_pgy_template",
            "base._delete_pgy_template_storage",
            "legacy_host",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
