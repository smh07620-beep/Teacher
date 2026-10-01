from pathlib import Path
import unittest

from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class ProductConvergence101Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shell = (ROOT / "static" / "product-convergence-101.js").read_text(encoding="utf-8")
        cls.plan = (ROOT / "PRODUCT_CONVERGENCE_20261001.md").read_text(encoding="utf-8")

    def test_convergence_asset_loads_after_existing_persona_shell(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertIn("/product-convergence-101.js", body)
        self.assertLess(body.index("/teacher-persona-isolation-1014.js"), body.index("/product-convergence-101.js"))

    def test_teacher_primary_navigation_has_only_two_product_jobs(self):
        self.assertIn("product-nav-course-101", self.shell)
        self.assertIn("product-nav-assessment-101", self.shell)
        self.assertEqual(self.shell.count("makeButton('product-nav-"), 2)
        self.assertIn("📚 教材與課程", self.shell)
        self.assertIn("📝 評量與出題", self.shell)

    def test_media_and_paper_export_remain_contextual_not_removed(self):
        self.assertIn("teacher-context-tools-101", self.shell)
        self.assertIn("🎙️ AI 媒體製作", self.shell)
        self.assertIn("📄 紙本文件與匯出", self.shell)
        self.assertIn("api.openMedia?.()", self.shell)
        self.assertIn("api.openDocuments?.()", self.shell)
        self.assertIn("不再各自佔一個主導覽", self.shell)

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
