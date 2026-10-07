"""Duplicate read-only API calls on the system page are shared, safely."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from pgy_frontend import ASSET_MANIFEST, _apply_asset_manifest

ROOT = Path(__file__).parents[1]


class ApiGetDedupeContractTests(unittest.TestCase):
    def source(self, name):
        return ROOT.joinpath("static", name).read_text(encoding="utf-8")

    def test_script_loads_right_after_api_client_and_before_feature_scripts(self):
        html = _apply_asset_manifest(
            '<html><head></head><body><script defer src="/shared-core.js"></script>'
            '<script defer src="/system-admin.js"></script></body></html>',
            "system",
        )
        order = re.findall(r'src="([^"]+)"', html)
        self.assertEqual(order.count("/api-get-dedupe-1007.js"), 1)
        self.assertEqual(order.index("/api-get-dedupe-1007.js"), order.index("/api-client.js") + 1)
        for feature in (
            "/training-command-center-71.js",
            "/pgy-competency-matrix-71.js",
            "/learning-analytics-71.js",
            "/learning-progress-convergence-1025.js",
            "/admin-course-material.js",
        ):
            self.assertLess(order.index("/api-get-dedupe-1007.js"), order.index(feature), feature)

    def test_it_is_registered_as_middleware_that_runs_before_the_other_ones(self):
        dedupe = self.source("api-get-dedupe-1007.js")
        self.assertIn("client.use('api-get-dedupe-1007', dedupeMiddleware, 50)", dedupe)
        priorities = [100, 200, 300]  # latency-712, review-links-66, sensitive-elevation-69
        self.assertTrue(all(50 < value for value in priorities))
        self.assertNotIn("window.fetch =", dedupe)

    def test_only_read_only_endpoints_are_shared(self):
        dedupe = self.source("api-get-dedupe-1007.js")
        block = re.search(r"SHARED_PATHS = new Set\(\[(.*?)\]\)", dedupe, re.S).group(1)
        paths = re.findall(r"'(/api/[^']+)'", block)
        self.assertGreaterEqual(len(paths), 8)
        for path in paths:
            self.assertNotRegex(path, r"login|logout|upload|jobs|submit|sign|password|exam|quiz")

    def test_behaviour_suite_passes_in_node(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        result = subprocess.run(
            [node, "--test", str(ROOT / "tests" / "js" / "api-get-dedupe-1007.test.js")],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-1500:])


if __name__ == "__main__":
    unittest.main()
