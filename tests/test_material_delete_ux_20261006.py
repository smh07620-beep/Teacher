import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MaterialDeleteUx20261006Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.course = ROOT.joinpath("static", "admin-course-material.js").read_text(encoding="utf-8")
        cls.materials = ROOT.joinpath("static", "admin-materials.js").read_text(encoding="utf-8")
        cls.upload = ROOT.joinpath("static", "admin-material-upload.js").read_text(encoding="utf-8")
        cls.csp = ROOT.joinpath("static", "system-csp-actions.js").read_text(encoding="utf-8")
        cls.rbac = ROOT.joinpath("teacher_app", "auth", "rbac_legacy_adapter.py").read_text(encoding="utf-8")

    def test_teacher_course_hub_exposes_normal_material_delete_directly(self):
        self.assertIn("🗑️ 刪除教材", self.course)
        self.assertIn("deleteAdminMaterial(\'${m.id}\')", self.course)
        self.assertIn("通用／未歸類", self.course)

    def test_all_materials_list_does_not_hide_delete_under_more_menu(self):
        self.assertIn("🗑️ 刪除教材", self.materials)
        self.assertNotIn("🗑️ 永久刪除", self.materials)

    def test_system_purge_is_visually_and_semantically_distinct(self):
        self.assertIn("系統永久清除…", self.course)
        self.assertIn("系統永久清除教材", self.course)
        self.assertIn("與一般「刪除教材」不同", self.course)

    def test_course_delete_explains_orphaned_material_behavior(self):
        self.assertIn("教材與考卷都會保留", self.course)
        self.assertIn("通用／未歸類", self.course)
        self.assertIn("重新關聯到其他課程", self.course)

    def test_normal_delete_keeps_existing_rbac_and_csp_contract(self):
        self.assertIn("\'deleteAdminMaterial\'", self.csp)
        self.assertIn("\"api_delete_slide\": (\"material.manage\", \"scoped\")", self.rbac)
        self.assertIn("method:\'DELETE\',credentials:\'same-origin\'", self.upload)


if __name__ == "__main__":
    unittest.main()
