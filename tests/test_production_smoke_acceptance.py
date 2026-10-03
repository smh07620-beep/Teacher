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
            'health_deployment.get("branch") == "main"',
            'observed == expected',
        ):
            self.assertIn(marker, source)

        self.assertNotIn('method="POST"', source)
        self.assertNotIn('method="PUT"', source)
        self.assertNotIn('method="PATCH"', source)
        self.assertNotIn('method="DELETE"', source)

    def test_workflow_runs_after_successful_release_checks_on_main(self):
        source = (ROOT / ".github" / "workflows" / "production-smoke.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_run:", source)
        self.assertIn("- Teacher release checks", source)
        self.assertIn("- main", source)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", source)
        self.assertIn("github.event.workflow_run.head_sha || github.sha", source)
        self.assertIn("tools/production_smoke.py", source)
        self.assertIn("production-smoke-report.json", source)

    def test_render_target_matches_existing_operational_workflows(self):
        smoke = (ROOT / ".github" / "workflows" / "production-smoke.yml").read_text(encoding="utf-8")
        keepalive = (ROOT / ".github" / "workflows" / "supabase-keepalive.yml").read_text(encoding="utf-8")
        fallback = (ROOT / ".github" / "workflows" / "material-fallback-worker.yml").read_text(encoding="utf-8")
        target = "https://teacher-j3id.onrender.com"
        self.assertIn(target, smoke)
        self.assertIn(target + "/health", keepalive)
        self.assertIn("TEACHER_BASE_URL: " + target, fallback)


if __name__ == "__main__":
    unittest.main()
