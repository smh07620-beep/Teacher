import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class StorageMaterialHotPathConvergenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ROOT.joinpath("app.py").read_text(encoding="utf-8")
        cls.entrypoint = ROOT.joinpath("pgy_app.py").read_text(encoding="utf-8")
        cls.storage = ROOT.joinpath("teacher_app/materials/storage.py").read_text(encoding="utf-8")

    def test_storage_pagination_patch_layer_is_retired(self):
        self.assertFalse(ROOT.joinpath("storage_pagination_hardening.py").exists())
        self.assertNotIn("install_storage_pagination_hardening", self.entrypoint)
        self.assertNotIn("storage_pagination_hardening", self.entrypoint)

    def test_r2_and_oci_use_canonical_bounded_storage_primitives(self):
        self.assertIn("from teacher_app.materials import storage as material_storage", self.app)
        self.assertIn("material_storage.delete_prefix(", self.app)
        self.assertIn("material_storage.bucket_usage_bytes(", self.app)
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

    def test_mega_session_cache_does_not_probe_whoami_on_each_hit(self):
        start = self.app.index("def _mega_login_if_needed")
        end = self.app.index("def _mega_remote_join", start)
        source = self.app[start:end]
        cache_branch = source[
            source.index('if (not force) and _MEGA_AUTH_CACHE.get("ok")'):
            source.index('probe = _mega_run(["mega-whoami"]', source.index('if (not force)'))
        ]
        self.assertIn("return", cache_branch)
        self.assertNotIn("mega-whoami", cache_branch)

    def test_preview_cache_is_size_evicted_not_time_expired(self):
        start = self.app.index("def _mega_cached_preview")
        end = self.app.index("def _mega_send_file", start)
        source = self.app[start:end]
        self.assertIn("valid = target.exists() and target.stat().st_size > 0", source)
        self.assertNotIn("MATERIAL_PREVIEW_CACHE_TTL_SECONDS", source)
        self.assertIn("_preview_cache_cleanup(protect=target)", source)

    def test_web_reads_have_total_budget_below_gunicorn_timeout(self):
        app = self.app
        render = ROOT.joinpath("render.yaml").read_text(encoding="utf-8")
        run_web = ROOT.joinpath("run_web.sh").read_text(encoding="utf-8")
        self.assertIn('MEGA_WEB_READ_TIMEOUT_SECONDS", "120"', app)
        self.assertIn("timeout_seconds=MEGA_WEB_READ_TIMEOUT_SECONDS", app)
        self.assertIn('key: MEGA_WEB_READ_TIMEOUT_SECONDS', render)
        self.assertIn('value: "120"', render)
        self.assertIn('key: GUNICORN_TIMEOUT', render)
        self.assertIn('value: "180"', render)
        self.assertIn('GUNICORN_TIMEOUT:-180', run_web)
    def test_mega_read_reauthenticates_once_only_after_real_failure(self):
        start = self.app.index("def mega_download_file")
        end = self.app.index("def mega_destroy", start)
        source = self.app[start:end]
        self.assertIn('_MEGA_AUTH_CACHE.update({"ok": False, "at": 0.0})', source)
        self.assertIn("_mega_login_if_needed(force=True, deadline=deadline)", source)


if __name__ == "__main__":
    unittest.main()
