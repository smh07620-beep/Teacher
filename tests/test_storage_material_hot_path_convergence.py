import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class StorageMaterialHotPathConvergenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ROOT.joinpath("app.py").read_text(encoding="utf-8")
        cls.entrypoint = ROOT.joinpath("pgy_app.py").read_text(encoding="utf-8")
        cls.storage = ROOT.joinpath("teacher_app/materials/storage.py").read_text(encoding="utf-8")
        cls.provider_storage = ROOT.joinpath("teacher_app/storage/providers.py").read_text(encoding="utf-8")
        cls.web_storage = ROOT.joinpath("teacher_app/storage/web_runtime.py").read_text(encoding="utf-8")

    def test_storage_pagination_patch_layer_is_retired(self):
        self.assertFalse(ROOT.joinpath("storage_pagination_hardening.py").exists())
        self.assertNotIn("install_storage_pagination_hardening", self.entrypoint)
        self.assertNotIn("storage_pagination_hardening", self.entrypoint)

    def test_r2_and_oci_use_canonical_bounded_storage_primitives(self):
        self.assertIn("from teacher_app.materials import storage as material_storage", self.web_storage)
        self.assertIn("material_storage.delete_prefix(", self.web_storage)
        for marker in (
            "MAX_STORAGE_PAGES",
            "NextContinuationToken",
            "StoragePaginationError",
            "def delete_prefix(",
            "def bucket_usage_bytes(",
        ):
            self.assertIn(marker, self.storage)

    def test_canonical_storage_module_has_no_provider_credentials(self):
        for forbidden in (
            "R2_SECRET_ACCESS_KEY",
            "OCI_SECRET_ACCESS_KEY",
            "MEGA_PASSWORD",
            "GDRIVE_CLIENT_SECRET",
            "boto3.client",
        ):
            self.assertNotIn(forbidden, self.storage)

    def test_live_provider_credentials_clients_and_mega_session_owner_moved_out_of_app(self):
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
            self.assertIn(marker, self.provider_storage)
            self.assertNotIn(marker, self.app)
        for delegate in (
            "providers.r2_client(",
            "providers.oci_client(",
            "providers.gdrive_service(",
            "providers.mega_login_if_needed(",
        ):
            self.assertIn(delegate, self.web_storage)

    def test_mega_session_cache_owner_is_canonical_and_does_not_probe_whoami_on_each_hit(self):
        self.assertNotIn('_MEGA_AUTH_CACHE = {"ok": False, "at": 0.0}', self.app)
        self.assertNotIn("_MEGA_LOCK = threading.RLock()", self.app)
        start = self.provider_storage.index("def mega_login_if_needed")
        source = self.provider_storage[start:]
        cache_branch = source[
            source.index('and _MEGA_AUTH_CACHE.get("ok")'):
            source.index('probe = run(', source.index('and _MEGA_AUTH_CACHE.get("ok")'))
        ]
        self.assertIn("return", cache_branch)
        self.assertNotIn("mega-whoami", cache_branch)

    def test_preview_cache_is_size_evicted_not_time_expired(self):
        start = self.web_storage.index("def mega_cached_preview")
        end = self.web_storage.index("def gdrive_find_file_in_folder", start)
        source = self.web_storage[start:end]
        self.assertIn("valid = target.exists() and target.stat().st_size > 0", source)
        self.assertNotIn("MATERIAL_PREVIEW_CACHE_TTL_SECONDS", source)
        self.assertIn("_preview_cache_cleanup(protect=target)", source)

    def test_web_reads_have_total_budget_below_gunicorn_timeout(self):
        render = ROOT.joinpath("render.yaml").read_text(encoding="utf-8")
        run_web = ROOT.joinpath("run_web.sh").read_text(encoding="utf-8")
        self.assertIn('MEGA_WEB_READ_TIMEOUT_SECONDS", "120"', self.provider_storage)
        self.assertIn("providers.MEGA_WEB_READ_TIMEOUT_SECONDS", self.web_storage)
        self.assertIn('key: MEGA_WEB_READ_TIMEOUT_SECONDS', render)
        self.assertIn('value: "120"', render)
        self.assertIn('key: GUNICORN_TIMEOUT', render)
        self.assertIn('value: "180"', render)
        self.assertIn('GUNICORN_TIMEOUT:-180', run_web)
    def test_mega_read_reauthenticates_once_only_after_real_failure(self):
        start = self.web_storage.index("def mega_download_file")
        end = self.web_storage.index("def mega_send_file", start)
        source = self.web_storage[start:end]
        self.assertIn("providers.invalidate_mega_auth_cache()", source)
        self.assertIn("force=True", source)
        self.assertEqual(source.count("providers.invalidate_mega_auth_cache()"), 1)


if __name__ == "__main__":
    unittest.main()
