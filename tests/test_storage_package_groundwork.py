import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from teacher_app.storage import (
    DeleteRequest,
    StorageConfigurationError,
    StorageDeletionError,
    StorageDeletionUnsupportedError,
    StorageProviderAdapter,
    delete_best_effort,
    delete_strict,
    normalize_backend,
    select_backend,
)
from teacher_app.storage import providers


ROOT = Path(__file__).parents[1]


def adapter(
    name,
    *,
    configured=False,
    present=False,
    block=False,
    delete_object=None,
    delete_prefix=None,
    delete_material=None,
    message="",
    partial_message="",
):
    return StorageProviderAdapter(
        name=name,
        is_configured=lambda: configured,
        has_configuration=lambda: present,
        block_auto_if_present=block,
        unavailable_message=message,
        partial_configuration_message=partial_message,
        delete_object=delete_object,
        delete_prefix=delete_prefix,
        delete_material=delete_material,
    )


class StoragePackageGroundworkTests(unittest.TestCase):
    def test_backend_normalization_preserves_legacy_auto_fallback(self):
        self.assertEqual(normalize_backend(" R2 "), "r2")
        self.assertEqual(normalize_backend(""), "auto")
        self.assertEqual(normalize_backend("future-provider"), "auto")

    def test_explicit_backend_requires_configured_transition_adapter(self):
        providers = {
            "gdrive": adapter(
                "gdrive",
                configured=False,
                message="Google Drive OAuth is incomplete",
            )
        }
        with self.assertRaisesRegex(StorageConfigurationError, "OAuth is incomplete"):
            select_backend("gdrive", providers)

        providers["gdrive"] = adapter("gdrive", configured=True)
        self.assertEqual(select_backend("gdrive", providers), "gdrive")

    def test_auto_selection_matches_current_provider_order(self):
        providers = {
            "mega": adapter("mega", configured=False),
            "oci": adapter("oci", configured=True),
            "gdrive": adapter("gdrive", configured=True),
            "r2": adapter("r2", configured=True),
        }
        self.assertEqual(select_backend("auto", providers), "oci")

    def test_auto_can_fail_closed_on_partial_primary_configuration(self):
        providers = {
            "mega": adapter(
                "mega",
                configured=False,
                present=True,
                block=True,
                message="explicit MEGA is unavailable",
                partial_message="MEGA settings are present but unusable",
            ),
            "gdrive": adapter("gdrive", configured=True),
        }
        with self.assertRaisesRegex(StorageConfigurationError, "MEGA settings"):
            select_backend("auto", providers)

    def test_auto_falls_back_to_local_without_creating_a_local_provider(self):
        providers = {
            "mega": adapter("mega", configured=False),
            "oci": adapter("oci", configured=False),
            "gdrive": adapter("gdrive", configured=False),
            "r2": adapter("r2", configured=False),
        }
        self.assertEqual(select_backend("auto", providers), "local")
        with self.assertRaises(StorageConfigurationError):
            select_backend("auto", providers, local_fallback=False)

    def test_strict_delete_dispatches_to_the_requested_provider_operation(self):
        calls = []
        providers = {
            "r2": adapter(
                "r2",
                configured=True,
                delete_prefix=lambda payload: calls.append(payload),
            )
        }
        result = delete_strict(
            DeleteRequest("r2", "prefix", "materials/upload-1/"),
            providers,
        )
        self.assertTrue(result.deleted)
        self.assertEqual(calls, ["materials/upload-1/"])

    def test_strict_delete_wraps_provider_failure_and_preserves_cause(self):
        failure = RuntimeError("provider rejected delete")

        def fail(_payload):
            raise failure

        providers = {
            "mega": adapter("mega", configured=True, delete_object=fail)
        }
        with self.assertRaises(StorageDeletionError) as caught:
            delete_strict(DeleteRequest("mega", "object", "/root/item"), providers)
        self.assertIs(caught.exception.cause, failure)
        self.assertIs(caught.exception.__cause__, failure)

    def test_best_effort_delete_reports_failure_without_raising(self):
        providers = {
            "gdrive": adapter(
                "gdrive",
                configured=True,
                delete_material=lambda _payload: (_ for _ in ()).throw(RuntimeError("boom")),
            )
        }
        result = delete_best_effort(
            DeleteRequest("gdrive", "material", {"materialFolderId": "folder-1"}),
            providers,
        )
        self.assertFalse(result.deleted)
        self.assertIsInstance(result.error, StorageDeletionError)

    def test_missing_delete_handler_is_explicit_in_strict_and_bounded_in_best_effort(self):
        providers = {"oci": adapter("oci", configured=True)}
        request = DeleteRequest("oci", "object", "key")
        with self.assertRaises(StorageDeletionUnsupportedError):
            delete_strict(request, providers)
        result = delete_best_effort(request, providers)
        self.assertFalse(result.deleted)
        self.assertIsInstance(result.error, StorageDeletionUnsupportedError)

    def test_policy_module_stays_provider_neutral(self):
        source = ROOT.joinpath("teacher_app/storage/service.py").read_text(encoding="utf-8")
        for forbidden in (
            "import app",
            "os.environ",
            "boto3",
            "google.oauth2",
            "googleapiclient",
            "AuthorizedSession",
            "subprocess",
            "MEGA_PASSWORD",
            "R2_SECRET_ACCESS_KEY",
            "OCI_SECRET_ACCESS_KEY",
            "GDRIVE_CLIENT_SECRET",
            "mega-login",
            "mega-whoami",
        ):
            self.assertNotIn(forbidden, source)

    def test_provider_runtime_is_the_only_storage_sdk_and_secret_loader(self):
        app = ROOT.joinpath("app.py").read_text(encoding="utf-8")
        provider_source = ROOT.joinpath("teacher_app/storage/providers.py").read_text(encoding="utf-8")
        for marker in (
            'os.environ.get("R2_SECRET_ACCESS_KEY"',
            'os.environ.get("OCI_SECRET_ACCESS_KEY"',
            'os.environ.get("GDRIVE_CLIENT_SECRET"',
            'os.environ.get("GDRIVE_REFRESH_TOKEN"',
            'os.environ.get("MEGA_PASSWORD"',
            "boto3.client(",
            "AuthorizedSession(",
            '_MEGA_AUTH_CACHE = {"ok": False, "at": 0.0}',
            "_MEGA_LOCK = threading.RLock()",
        ):
            self.assertIn(marker, provider_source)
            self.assertNotIn(marker, app)

    def test_r2_client_is_constructed_by_canonical_provider_runtime(self):
        boto = Mock()
        boto.client.return_value = object()
        with patch.object(providers, "boto3", boto), patch.object(providers, "BotoConfig", None):
            result = providers.r2_client(
                account_id="acct",
                access_key_id="key",
                secret_access_key="secret",
                bucket_name="bucket",
            )
        self.assertIs(result, boto.client.return_value)
        self.assertEqual(
            boto.client.call_args.kwargs["endpoint_url"],
            "https://acct.r2.cloudflarestorage.com",
        )

    def test_mega_login_cache_is_canonically_owned_and_reused(self):
        providers.invalidate_mega_auth_cache()
        calls = []

        def run(args, **kwargs):
            calls.append((list(args), kwargs))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        providers.mega_login_if_needed(
            is_configured=lambda: True,
            run=run,
            email="teacher@example.test",
            password="secret",
            session_cache_seconds=1800,
        )
        first_count = len(calls)
        providers.mega_login_if_needed(
            is_configured=lambda: True,
            run=run,
            email="teacher@example.test",
            password="secret",
            session_cache_seconds=1800,
        )
        self.assertEqual(first_count, 2)
        self.assertEqual(len(calls), first_count)


if __name__ == "__main__":
    unittest.main()
