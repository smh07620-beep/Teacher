import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app as appmod
from teacher_app import storage as canonical_storage
from teacher_app.storage import providers as storage_providers
from teacher_app.common.errors import ApiError
from teacher_app.materials import service as material_service


class StorageDeletionConvergenceTests(unittest.TestCase):
    def test_runtime_adapter_builder_dispatches_without_owning_clients(self):
        calls = []
        adapters = canonical_storage.build_delete_adapters(
            mega_is_configured=lambda: True,
            mega_delete_object=lambda value: calls.append(("mega", value)),
            gdrive_is_configured=lambda: True,
            gdrive_delete_object=lambda value: calls.append(("gdrive", value)),
            oci_is_configured=lambda: True,
            oci_delete_object=lambda value: calls.append(("oci", value)),
            r2_is_configured=lambda: True,
            r2_delete_object=lambda value: calls.append(("r2", value)),
        )

        canonical_storage.delete_strict(
            canonical_storage.DeleteRequest("oci", "object", "oci-key"),
            adapters,
        )
        self.assertEqual(calls, [("oci", "oci-key")])

    def test_mega_strict_delete_does_not_swallow_provider_failure(self):
        storage_providers.invalidate_mega_auth_cache()
        calls = []

        def run(args, **kwargs):
            calls.append((list(args), dict(kwargs)))
            if args[0] == "mega-rm":
                self.assertTrue(kwargs["check"])
                raise RuntimeError("remote delete failed")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with self.assertRaisesRegex(RuntimeError, "remote delete failed"):
            storage_providers.mega_delete_object(
                "/materials/item",
                is_configured=lambda: True,
                run=run,
                email="teacher@example.test",
                password="secret",
            )
        self.assertEqual(calls[-1][0], ["mega-rm", "-r", "-f", "/materials/item"])

    def test_staging_delete_uses_canonical_object_delete_before_r2_ledger(self):
        with patch.object(appmod, "_delete_storage_object") as delete, patch.object(
            appmod, "r2_record_deleted"
        ) as record:
            appmod.delete_material_job_staging(
                {"stagingBackend": "r2", "stagingKey": "_staging/job/source.pptx"}
            )
        delete.assert_called_once()
        self.assertEqual(delete.call_args.args[:2], ("r2", "_staging/job/source.pptx"))
        record.assert_called_once_with("_staging/job/source.pptx")

        with patch.object(appmod, "_delete_storage_object", side_effect=RuntimeError("delete failed")), patch.object(
            appmod, "r2_record_deleted"
        ) as record:
            with self.assertRaisesRegex(RuntimeError, "delete failed"):
                appmod.delete_material_job_staging(
                    {"stagingBackend": "r2", "stagingKey": "_staging/job/source.pptx"}
                )
        record.assert_not_called()

    def _material_base(self, mega_delete):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)

        def adapters(**kwargs):
            return canonical_storage.build_delete_adapters(
                mega_is_configured=lambda: True,
                mega_delete_object=mega_delete,
                gdrive_is_configured=lambda: True,
                gdrive_delete_object=lambda _value: None,
                gdrive_delete_material=lambda _value: None,
                oci_is_configured=lambda: True,
                oci_delete_object=lambda _value: None,
                oci_delete_prefix=lambda _value: None,
                r2_is_configured=lambda: True,
                r2_delete_object=lambda _value: None,
                r2_delete_prefix=lambda _value: None,
                **kwargs,
            )

        return SimpleNamespace(
            UPLOAD_DIR=root / "uploads",
            UPLOADED_SLIDES_DIR=root / "slides",
            PREVIEW_CACHE_DIR=root / "preview",
            storage_delete_adapters=adapters,
        )

    def test_material_delete_uses_canonical_strict_delete_before_db_row(self):
        calls = []
        base = self._material_base(lambda value: calls.append(value))
        entry = {
            "id": "upload-1",
            "folder": "upload-1",
            "storageBackend": "mega",
            "storageKey": "/materials/upload-1/source.pptx",
            "storageMeta": {"folderId": "/materials/upload-1"},
        }
        with patch.object(material_service.repository, "get_material", return_value=entry), patch.object(
            material_service.repository, "delete_material_record"
        ) as delete_record:
            result = material_service.delete_material(base, "upload-1")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, ["/materials/upload-1"])
        delete_record.assert_called_once_with("upload-1")

    def test_material_delete_failure_keeps_db_row_and_maps_to_502(self):
        def fail(_value):
            raise RuntimeError("provider unavailable")

        base = self._material_base(fail)
        entry = {
            "id": "upload-1",
            "folder": "upload-1",
            "storageBackend": "mega",
            "storageMeta": {"folderId": "/materials/upload-1"},
        }
        with patch.object(material_service.repository, "get_material", return_value=entry), patch.object(
            material_service.repository, "delete_material_record"
        ) as delete_record:
            with self.assertRaises(ApiError) as caught:
                material_service.delete_material(base, "upload-1")
        self.assertEqual(caught.exception.status, 502)
        self.assertEqual(caught.exception.code, "MEGA_DELETE_FAILED")
        delete_record.assert_not_called()

    def test_doc_template_admin_delete_failure_keeps_metadata_row(self):
        failure = canonical_storage.StorageDeletionError("r2", "object", RuntimeError("delete failed"))
        row = {"storage_backend": "r2", "storage_key": "doc/key", "storage_filename": "grpBio.docx"}
        with appmod.app.test_request_context("/api/doc-templates/grpBio", method="DELETE"), patch.object(
            appmod, "require_admin", return_value=None
        ), patch.object(appmod, "get_doc_template_row", return_value=row), patch.object(
            appmod, "_delete_doc_template_storage", side_effect=failure
        ), patch.object(appmod, "delete_doc_template_row") as delete_row:
            response, status = appmod.api_delete_doc_template("grpBio")
        self.assertEqual(status, 502)
        self.assertIn("Word 範本刪除失敗", response.get_json()["error"])
        delete_row.assert_not_called()

    def test_pgy_admin_delete_failure_keeps_metadata_row(self):
        failure = canonical_storage.StorageDeletionError("oci", "object", RuntimeError("delete failed"))
        row = {"storage_backend": "oci", "storage_key": "pgy/key", "filename": "epa.pdf"}
        with appmod.app.test_request_context("/api/pgy-assessment-templates/epa", method="DELETE"), patch.object(
            appmod, "require_admin", return_value=None
        ), patch.object(appmod, "_get_pgy_template", return_value=row), patch.object(
            appmod, "_delete_pgy_template_storage", side_effect=failure
        ), patch.object(appmod, "_db_conn") as db_conn:
            response, status = appmod.api_delete_pgy_assessment_template("epa")
        self.assertEqual(status, 502)
        self.assertIn("評量範本刪除失敗", response.get_json()["error"])
        db_conn.assert_not_called()

    def test_pgy_storage_delete_includes_oci_and_can_be_strict(self):
        sentinel = object()
        with patch.object(appmod, "_delete_storage_object", return_value=sentinel) as delete:
            result = appmod._delete_pgy_template_storage(
                {"storage_backend": "oci", "storage_key": "pgy/key"},
                best_effort=False,
            )
        self.assertIs(result, sentinel)
        self.assertEqual(delete.call_args.args[:2], ("oci", "pgy/key"))
        self.assertFalse(delete.call_args.kwargs["best_effort"])

    def test_replacement_cleanup_paths_are_best_effort(self):
        source = Path(appmod.__file__).read_text(encoding="utf-8")
        self.assertIn("_delete_doc_template_storage(old, best_effort=True)", source)
        self.assertIn("storage_created = False", source)
        self.assertIn("old_local_same_path = bool(", source)
        self.assertIn("if storage_created and not old_local_same_path:", source)
        self.assertIn("def _delete_pgy_template_storage(row, *, best_effort=True):", source)


if __name__ == "__main__":
    unittest.main()
