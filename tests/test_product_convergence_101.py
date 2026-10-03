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
        self.assertIn("📝 評量與出題", self.persona)
        self.assertIn("teacherButtons.length !== 2", self.persona)

    def test_media_and_paper_export_remain_contextual_not_removed(self):
        self.assertIn("teacher-context-tools-101", self.shell)
        self.assertIn("🎙️ AI 媒體製作", self.shell)
        self.assertIn("📄 紙本文件與匯出", self.shell)
        self.assertIn("api.openMedia?.()", self.shell)
        self.assertIn("api.openDocuments?.()", self.shell)
        self.assertIn("不再各自佔一個主導覽", self.shell)

    def test_teacher_and_convergence_layers_do_not_compete_for_navigation(self):
        self.assertIn("final teacher persona navigation is owned by teacher-persona-isolation", self.shell)
        self.assertNotIn("navHost.replaceChildren(group)", self.shell)
        self.assertIn("contextual tools and never rewrites the navigation host", self.shell)

    def test_system_navigation_delegates_to_the_single_focus_owner(self):
        self.assertIn("window.SystemAdminFocus1014", self.shell)
        self.assertIn("owner.rebuild()", self.shell)
        self.assertNotIn("navHost.replaceChildren", self.shell)
        self.assertNotIn("function existing(id, label = '')", self.shell)
        self.assertIn("delegates to the sole", self.shell)

    def test_system_nav_observer_only_requests_canonical_reconciliation(self):
        self.assertIn("const observer = new MutationObserver(() => refresh())", self.shell)
        self.assertIn("if (isSystemPersona()) convergeSystemNavigation()", self.shell)

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
