from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parents[1]


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
            '"6.8.1"',
            "_dns_diagnostic",
            '"stage": "dns"',
            'health_deployment.get("branch") == "main"',
            'observed == expected',
        ):
            self.assertIn(marker, source)

        self.assertNotIn('method="POST"', source)
        self.assertNotIn('method="PUT"', source)
        self.assertNotIn('method="PATCH"', source)
        self.assertNotIn('method="DELETE"', source)

    def test_workflow_is_post_deploy_and_does_not_deadlock_render_checks_pass(self):
        source = (ROOT / ".github" / "workflows" / "production-smoke.yml").read_text(encoding="utf-8")
        render = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("autoDeployTrigger: checksPass", render)
        self.assertIn("schedule:", source)
        self.assertIn('cron: "*/5 * * * *"', source)
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("workflow_run:", source)
        self.assertNotRegex(source, r"(?m)^\s*push:\s*$")
        self.assertIn("EXPECTED_COMMIT: ${{ github.sha }}", source)
        self.assertIn("tools/production_smoke.py", source)
        self.assertIn("production-smoke-report.json", source)
        self.assertIn("circular gate", source)

    def test_render_target_matches_existing_operational_workflows(self):
        smoke = (ROOT / ".github" / "workflows" / "production-smoke.yml").read_text(encoding="utf-8")
        keepalive = (ROOT / ".github" / "workflows" / "supabase-keepalive.yml").read_text(encoding="utf-8")
        fallback = (ROOT / ".github" / "workflows" / "material-fallback-worker.yml").read_text(encoding="utf-8")
        target = "https://teacher-j3id.onrender.com"
        override = "${{ vars.TEACHER_PRODUCTION_URL || '" + target + "' }}"

        self.assertIn("TEACHER_PRODUCTION_URL: " + override, smoke)
        self.assertIn("TEACHER_PRODUCTION_URL: " + override, keepalive)
        self.assertIn("TEACHER_BASE_URL: " + override, fallback)
        self.assertIn('--base-url "$TEACHER_PRODUCTION_URL"', smoke)
        self.assertIn('"${TEACHER_PRODUCTION_URL%/}/health"', keepalive)
        self.assertIn("socket.getaddrinfo", keepalive)
        self.assertIn("socket.getaddrinfo", fallback)


if __name__ == "__main__":
    unittest.main()
