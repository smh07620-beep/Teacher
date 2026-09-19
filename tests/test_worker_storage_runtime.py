"""Focused regressions for the Flask-free local-worker storage adapter."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter


ROOT = Path(__file__).parents[1]


class _Request:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class _DriveFiles:
    def __init__(self):
        self.created = []
        self.deleted = []

    def create(self, *, body, media_body=None, fields=""):
        self.created.append((body, media_body, fields))
        if body.get("mimeType") == "application/vnd.google-apps.folder":
            return _Request({"id": "folder-1", "name": body["name"]})
        return _Request({"id": "source-1", "name": body["name"]})

    def delete(self, *, fileId):
        self.deleted.append(fileId)
        return _Request({})


class _DriveService:
    def __init__(self):
        self.files_api = _DriveFiles()

    def files(self):
        return self.files_api


class WorkerStorageRuntimeTests(unittest.TestCase):
    def test_qpdf_check_rejects_structurally_invalid_pdf(self):
        adapter = WorkerMaterialStorageAdapter()
        with tempfile.TemporaryDirectory() as temp_name:
            pdf = Path(temp_name) / "source.pdf"
            pdf.write_bytes(b"%PDF-1.7\n")
            invalid = SimpleNamespace(returncode=2, stdout=b"", stderr=b"invalid xref")
            with patch("teacher_app.storage.worker_runtime.shutil.which", return_value="qpdf"), patch(
                "teacher_app.storage.worker_runtime.subprocess.run", return_value=invalid
            ):
                with self.assertRaisesRegex(RuntimeError, "qpdf"):
                    adapter._linearize_pdf_in_place(pdf)

    def test_qpdf_checks_before_and_after_linearization(self):
        adapter = WorkerMaterialStorageAdapter()
        calls = []
        with tempfile.TemporaryDirectory() as temp_name:
            pdf = Path(temp_name) / "source.pdf"
            pdf.write_bytes(b"%PDF-1.7\n")

            def run(args, **_kwargs):
                calls.append(list(args))
                if "--linearize" in args:
                    Path(args[-1]).write_bytes(b"%PDF-1.7\nlinearized")
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

            with patch("teacher_app.storage.worker_runtime.shutil.which", return_value="qpdf"), patch(
                "teacher_app.storage.worker_runtime.subprocess.run", side_effect=run
            ):
                self.assertTrue(adapter._linearize_pdf_in_place(pdf))
        self.assertEqual(sum("--check" in call for call in calls), 2)
        self.assertEqual(sum("--linearize" in call for call in calls), 1)

    def test_runtime_module_has_no_flask_or_legacy_app_dependency(self):
        source = ROOT.joinpath(
            "teacher_app", "storage", "worker_runtime.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("from flask", source)
        self.assertNotIn("import app", source)
        self.assertNotIn("boto3.client", source)
        self.assertNotIn("GoogleCredentials", source)

    def test_auto_backend_uses_canonical_provider_availability(self):
        adapter = WorkerMaterialStorageAdapter()
        adapter.requested_backend = "auto"
        with (
            patch.object(adapter, "mega_is_configured", return_value=False),
            patch(
                "teacher_app.storage.worker_runtime.providers.mega_credentials_present",
                return_value=False,
            ),
            patch(
                "teacher_app.storage.worker_runtime.providers.oci_is_configured",
                return_value=False,
            ),
            patch(
                "teacher_app.storage.worker_runtime.providers.gdrive_is_configured",
                return_value=True,
            ),
            patch(
                "teacher_app.storage.worker_runtime.providers.r2_is_configured",
                return_value=False,
            ),
        ):
            self.assertEqual(adapter.active_backend(), "gdrive")

    def test_gdrive_upload_reuses_one_canonical_service(self):
        adapter = WorkerMaterialStorageAdapter()
        service = _DriveService()
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            source = temp / "source.txt"
            source.write_text("worker material", encoding="utf-8")
            slides = temp / "slides"
            slides.mkdir()
            with (
                patch(
                    "teacher_app.storage.worker_runtime.providers.gdrive_service",
                    return_value=service,
                ) as service_factory,
                patch(
                    "teacher_app.storage.worker_runtime.providers.gdrive_media_file_upload",
                    return_value=object(),
                ),
            ):
                key, prefix, meta = adapter.upload_material_tree_to_gdrive(
                    "material-1",
                    source,
                    slides,
                    0,
                    original_name="lesson.txt",
                )
        service_factory.assert_called_once_with()
        self.assertEqual(key, "source-1")
        self.assertEqual(prefix, "")
        self.assertEqual(meta["materialFolderId"], "folder-1")
        self.assertEqual(meta["sourceFileId"], "source-1")

    def test_gdrive_document_upload_publishes_index_derivative(self):
        adapter = WorkerMaterialStorageAdapter()
        service = _DriveService()
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            source = temp / "source.pdf"
            source.write_bytes(b"pdf")
            index = temp / "index.txt"
            index.write_text("全文索引", encoding="utf-8")
            slides = temp / "slides"
            slides.mkdir()
            with (
                patch(
                    "teacher_app.storage.worker_runtime.providers.gdrive_service",
                    return_value=service,
                ),
                patch(
                    "teacher_app.storage.worker_runtime.providers.gdrive_media_file_upload",
                    return_value=object(),
                ),
            ):
                _key, _prefix, meta = adapter.upload_material_tree_to_gdrive(
                    "material-1",
                    source,
                    slides,
                    0,
                    original_name="lesson.pdf",
                    derivatives={"index.txt": index},
                )
        self.assertEqual(meta["derivedFiles"]["index.txt"], "source-1")
        names = [body["name"] for body, _media, _fields in service.files_api.created]
        self.assertIn("index.txt", names)


if __name__ == "__main__":
    unittest.main()
