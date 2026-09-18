import os
import unittest
from unittest.mock import patch

import pgy_frontend


class FrontendRuntimeCacheValidationTests(unittest.TestCase):
    def test_render_commit_rewrites_same_origin_js_and_css_cache_keys(self):
        html = (
            '<script defer src="/teacher-content-studio-71.js?v=7116"></script>'
            '<link rel="stylesheet" href="/learner.css?v=5900">'
            '<script src="https://cdn.example.test/lib.js?v=1"></script>'
        )
        with patch.dict(os.environ, {"RENDER_GIT_COMMIT": "abcdef1234567890abcdef1234567890abcdef12"}, clear=False):
            rewritten = pgy_frontend._rewrite_local_asset_versions(html)

        self.assertIn('src="/teacher-content-studio-71.js?v=abcdef123456"', rewritten)
        self.assertIn('href="/learner.css?v=abcdef123456"', rewritten)
        self.assertIn('src="https://cdn.example.test/lib.js?v=1"', rewritten)
        self.assertNotIn('teacher-content-studio-71.js?v=7116', rewritten)

    def test_explicit_asset_version_overrides_render_commit(self):
        with patch.dict(
            os.environ,
            {"ASSET_VERSION": "rc-live-1", "RENDER_GIT_COMMIT": "abcdef1234567890"},
            clear=False,
        ):
            self.assertEqual(pgy_frontend._runtime_asset_version(), "rc-live-1")

    def test_local_fallback_is_stable_and_nonempty(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(pgy_frontend._runtime_asset_version())


if __name__ == "__main__":
    unittest.main()
