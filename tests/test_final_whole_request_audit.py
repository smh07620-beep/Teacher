from pathlib import Path
import re
import unittest

import release_contract


ROOT = Path(__file__).resolve().parents[1]


class FinalWholeRequestAuditTests(unittest.TestCase):
    def test_release_identity_and_current_branch_are_aligned(self):
        version = ROOT.joinpath("VERSION").read_text(encoding="utf-8").strip()
        architecture = ROOT.joinpath("ARCHITECTURE.md").read_text(encoding="utf-8")
        workflow = ROOT.joinpath(".github", "workflows", "phase3-pgy-checks.yml").read_text(encoding="utf-8")
        self.assertEqual(version, "6.8.1")
        self.assertEqual(release_contract.RELEASE_VERSION, version)
        self.assertEqual(release_contract.INTERNAL_GENERATION, "7.9 / RC79")
        self.assertIn("Formal release SemVer is `6.8.1`", architecture)
        self.assertIn("7.9 / RC79", architecture)
        push = workflow.split("pull_request:", 1)[0]
        self.assertRegex(push, r"(?m)^\s+- main\s*$")
        self.assertNotIn("feature/teacher-content-authoring-studio-72", push)
        self.assertNotIn("codex/phase-3-pgy-architecture", push)

    def test_retired_exam_browser_asset_is_not_a_runtime_owner(self):
        matrix = ROOT.joinpath("RC_FEATURE_UI_COVERAGE_MATRIX.md").read_text(encoding="utf-8")
        architecture = ROOT.joinpath("ARCHITECTURE.md").read_text(encoding="utf-8")
        self.assertFalse(ROOT.joinpath("static", "exam-integrity.js").exists())
        self.assertIn("`static/system-exam.js`", matrix)
        self.assertNotIn("`static/exam-integrity.js`", matrix)
        self.assertIn("retired no-op `static/exam-integrity.js`", architecture)

    def test_no_unreferenced_static_javascript_assets_remain(self):
        runtime_text = ROOT.joinpath("teacher_app", "frontend", "assets.py").read_text(encoding="utf-8")
        runtime_text += "\n".join(
            path.read_text(encoding="utf-8")
            for path in ROOT.joinpath("static").glob("*.html")
        )
        unreferenced = []
        for path in ROOT.joinpath("static").glob("*.js"):
            name = path.name
            if (
                f"/{name}" not in runtime_text
                and f'src="{name}"' not in runtime_text
                and f"src='{name}'" not in runtime_text
            ):
                unreferenced.append(name)
        self.assertEqual([], sorted(unreferenced))

    def test_group_leader_all_assignment_is_ui_wide_but_scope_fail_closed(self):
        routes = ROOT.joinpath("teacher_app", "learning", "assignment_routes.py").read_text(encoding="utf-8")
        service = ROOT.joinpath("teacher_app", "learning", "assignment_service.py").read_text(encoding="utf-8")
        matrix = ROOT.joinpath("RC_FEATURE_UI_COVERAGE_MATRIX.md").read_text(encoding="utf-8")
        self.assertIn('allowed.append("all")', routes)
        self.assertIn('body["allScope"] = "course_group"', routes)
        self.assertIn('data["assigneeType"] = "group"', routes)
        self.assertIn('if assignment_area != own_area or assignment_group != own_group', service)
        self.assertIn('assignee_type not in {"group", "user"}', service)
        self.assertIn("group leader may choose `全體人員`", matrix)

    def test_security_and_rate_limit_topology_match_deployment(self):
        render = ROOT.joinpath("render.yaml").read_text(encoding="utf-8")
        run_web = ROOT.joinpath("run_web.sh").read_text(encoding="utf-8")
        config = ROOT.joinpath("teacher_app", "config.py").read_text(encoding="utf-8")
        security = ROOT.joinpath("teacher_app", "common", "security.py").read_text(encoding="utf-8")
        self.assertIn("numInstances: 1", render)
        self.assertIn("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", render)
        self.assertIn("LOGIN_RATE_LIMIT_WINDOW_SECONDS", render)
        self.assertIn("PRODUCTION_REQUIRE_SECRET", render)
        self.assertIn("SECRET_KEY", render)
        self.assertIn("MATERIAL_WORKER_TOKEN", render)
        self.assertIn("WEB_CONCURRENCY:-1", run_web)
        self.assertIn("login_rate_limit_process_local", config)
        self.assertIn('"backend": "process-local"', security)
        self.assertIn("Production requires SECRET_KEY with at least 32 characters.", security)

    def test_production_factory_and_ci_guards_stay_canonical(self):
        factory = ROOT.joinpath("teacher_app", "factory.py").read_text(encoding="utf-8")
        workflow = ROOT.joinpath(".github", "workflows", "phase3-pgy-checks.yml").read_text(encoding="utf-8")
        self.assertNotIn("legacy_host", factory)
        self.assertNotIn("load_legacy_app", factory)
        self.assertIn("test_frontend_ownership_ci_guard.py", workflow)
        self.assertIn("test_final_whole_request_audit.py", workflow)
        self.assertIn("Browser JavaScript syntax", workflow)
        self.assertIn("PostgreSQL 16 factory and migration contracts", workflow)


if __name__ == "__main__":
    unittest.main()
