from pathlib import Path
import unittest

from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class ProductConvergence101Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shell = (ROOT / "static" / "product-convergence-101.js").read_text(encoding="utf-8")
        cls.persona = (ROOT / "static" / "teacher-persona-isolation-1014.js").read_text(encoding="utf-8")
        cls.plan = (ROOT / "PRODUCT_CONVERGENCE_20261001.md").read_text(encoding="utf-8")

    def test_convergence_asset_loads_after_existing_persona_shell(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertIn("/product-convergence-101.js", body)
        self.assertLess(body.index("/teacher-persona-isolation-1014.js"), body.index("/product-convergence-101.js"))

    def test_teacher_primary_navigation_has_only_two_product_jobs(self):
        self.assertIn("teacher-nav-course-1014", self.persona)
        self.assertIn("teacher-nav-assessment-1014", self.persona)
        self.assertEqual(self.persona.count("['teacher-nav-"), 2)
        self.assertIn("📚 教材與課程", self.persona)
        self.assertIn("📝 評量與追蹤", self.persona)
        self.assertIn("teacherButtons.length !== 2", self.persona)

    def test_duplicate_extension_card_is_removed_after_contextual_routes_moved(self):
        self.assertIn("document.getElementById('teacher-context-tools-101')?.remove()", self.shell)
        self.assertNotIn("teacher-context-media-101", self.shell)
        self.assertNotIn("teacher-context-documents-101", self.shell)
        self.assertIn("AI 製作從教材流程內開啟", self.shell)
        self.assertIn("公告、文件與使用導覽在右上工具", self.shell)

    def test_teacher_and_convergence_layers_do_not_compete_for_navigation(self):
        self.assertIn("final teacher persona navigation is owned by teacher-persona-isolation", self.shell)
        self.assertIn("Structural system navigation is owned by workspace-shell-70.js", self.shell)
        self.assertNotIn("navHost.replaceChildren", self.shell)
        self.assertIn("This layer only adds contextual tools and stable presentation labels", self.shell)
        self.assertIn("not rebuild either navigation tree", self.shell)

    def test_system_navigation_groups_infrastructure_by_human_job(self):
        for label in ("人員與權限", "系統健康與維運", "安全與稽核"):
            self.assertIn(label, self.shell)
        for existing_id in (
            "admin-nav-people",
            "admin-nav-system",
            "admin-nav-worker",
            "admin-nav-maintenance",
            "admin-nav-audit",
        ):
            self.assertIn(existing_id, self.shell)

    def test_system_nav_observer_does_not_self_trigger_on_stable_labels(self):
        self.assertIn("if (label && button.textContent !== label) button.textContent = label;", self.shell)
        self.assertIn("if (label && label.textContent !== text) label.textContent = text;", self.shell)
        self.assertNotIn("navGroup('系統健康與維運'", self.shell)

    def test_convergence_does_not_create_authorization_logic_or_secret_headers(self):
        self.assertIn("TeacherRBAC681Ready", self.shell)
        self.assertNotIn("X-Admin-Key", self.shell)
        self.assertNotIn("ADMIN_KEY", self.shell)
        self.assertNotIn("fetch('/api/", self.shell)

    def test_plan_defines_operational_done_and_golden_paths(self):
        self.assertIn("Definition of Done for a feature", self.plan)
        for golden_path in range(1, 9):
            self.assertIn(f"GP-{golden_path:02d}", self.plan)
        self.assertIn("A green unit/API suite is no longer sufficient", self.plan)
        self.assertIn("GP-01/GP-05", self.plan)


if __name__ == "__main__":
    unittest.main()
