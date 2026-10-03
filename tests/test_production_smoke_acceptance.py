from pathlib import Path
import ast
import http.client
import importlib.util
import re
import socket
import sys
import unittest
from unittest import mock
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]


def _load_smoke_module():
    path = ROOT / "tools" / "production_smoke.py"
    spec = importlib.util.spec_from_file_location("production_smoke_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeHTTPResponse:
    def __init__(self, status: int, body: bytes = b"ok"):
        self._status = status
        self._body = body
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self):
        return self._status

    def read(self):
        return self._body


class ProductionSmokeAcceptanceTests(unittest.TestCase):
    def test_probe_is_read_only_and_checks_exact_deployment(self):
        path = ROOT / "tools" / "production_smoke.py"
        source = path.read_text(encoding="utf-8")
        ast.parse(source)

        for marker in (
            '"/health"',
            '"/ready"',
            '"/live"',
            '"/api/auth/me"',
            '"/system"',
            '"今天的學習，從這裡開始"',
            "EXPECTED_VERSION",
            'ROOT.joinpath("VERSION")',
            "_dns_diagnostic",
            '"stage": "dns"',
            "_commit_matches",
            "RETRYABLE_HTTP_STATUSES",
            "http.client.HTTPException",
            '"failedStage"',
            'health_deployment.get("branch") == "main"',
        ):
            self.assertIn(marker, source)

        self.assertNotIn('method="POST"', source)
        self.assertNotIn('method="PUT"', source)
        self.assertNotIn('method="PATCH"', source)
        self.assertNotIn('method="DELETE"', source)
        self.assertNotIn('"6.8.1"', source)
        self.assertNotIn("urlopen", source)


    def test_request_retries_transient_network_and_protocol_errors(self):
        smoke = _load_smoke_module()
        opener = mock.Mock()
        opener.open.side_effect = [
            URLError(socket.gaierror(-3, "temporary failure in name resolution")),
            http.client.BadStatusLine("truncated"),
            _FakeHTTPResponse(200),
        ]

        with mock.patch.object(smoke, "build_opener", return_value=opener), mock.patch.object(
            smoke.time, "sleep", return_value=None
        ):
            response = smoke._request(
                "https://example.invalid",
                "/ready",
                timeout=1,
                attempts=3,
                retry_delay=0,
            )

        self.assertEqual(response.status, 200)
        self.assertEqual(opener.open.call_count, 3)

    def test_request_retries_retryable_gateway_statuses(self):
        smoke = _load_smoke_module()
        opener = mock.Mock()
        opener.open.side_effect = [_FakeHTTPResponse(503), _FakeHTTPResponse(200)]

        with mock.patch.object(smoke, "build_opener", return_value=opener), mock.patch.object(
            smoke.time, "sleep", return_value=None
        ):
            response = smoke._request(
                "https://example.invalid",
                "/login",
                timeout=1,
                attempts=3,
                retry_delay=0,
            )

        self.assertEqual(response.status, 200)
        self.assertEqual(opener.open.call_count, 2)

    def test_workflow_is_post_deploy_and_does_not_deadlock_render_checks_pass(self):
        source = (ROOT / ".github" / "workflows" / "production-smoke.yml").read_text(encoding="utf-8")
        render = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("autoDeployTrigger: checksPass", render)
        self.assertIn("schedule:", source)
        self.assertIn('cron: "*/15 * * * *"', source)
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("workflow_run:", source)
        self.assertNotRegex(source, r"(?m)^\s*push:\s*$")
        self.assertIn("EXPECTED_COMMIT: ${{ github.sha }}", source)
        self.assertIn("tools/production_smoke.py", source)
        self.assertIn("production-smoke-report.json", source)
        self.assertIn("circular gate", source)
        self.assertIn("cancel-in-progress: false", source)
        self.assertIn("--max-wait-seconds 720", source)
        self.assertIn("timeout-minutes: 30", source)

    def test_keepalive_retry_budget_fits_job_timeout(self):
        source = (ROOT / ".github" / "workflows" / "supabase-keepalive.yml").read_text(encoding="utf-8")
        self.assertIn("timeout-minutes: 12", source)
        self.assertIn("--retry 4", source)
        self.assertIn("--max-time 60", source)

    def test_render_target_matches_existing_operational_workflows(self):
        smoke = (ROOT / ".github" / "workflows" / "production-smoke.yml").read_text(encoding="utf-8")
        keepalive = (ROOT / ".github" / "workflows" / "supabase-keepalive.yml").read_text(encoding="utf-8")
        fallback = (ROOT / ".github" / "workflows" / "material-fallback-worker.yml").read_text(encoding="utf-8")
        def target_from(source: str) -> str:
            match = re.search(r"vars\.TEACHER_PRODUCTION_URL\s*\|\|\s*'([^']+)'", source)
            self.assertIsNotNone(match)
            return match.group(1)

        targets = [target_from(smoke), target_from(keepalive), target_from(fallback)]
        self.assertEqual(targets[0], targets[1])
        self.assertEqual(targets[0], targets[2])
        override = "${{ vars.TEACHER_PRODUCTION_URL || '" + targets[0] + "' }}"

        self.assertIn("TEACHER_PRODUCTION_URL: " + override, smoke)
        self.assertIn("TEACHER_PRODUCTION_URL: " + override, keepalive)
        self.assertIn("TEACHER_BASE_URL: " + override, fallback)
        self.assertIn('--base-url "$TEACHER_PRODUCTION_URL"', smoke)
        self.assertIn('"${TEACHER_PRODUCTION_URL%/}/health"', keepalive)
        self.assertIn("socket.getaddrinfo", keepalive)
        self.assertIn("socket.getaddrinfo", fallback)


if __name__ == "__main__":
    unittest.main()
