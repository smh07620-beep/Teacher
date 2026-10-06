import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ClinicalCourseMaterialRegression20261006Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wizard = ROOT.joinpath("static", "course-wizard-681.js").read_text(encoding="utf-8")
        cls.runtime = ROOT.joinpath("static", "course-wizard-runtime-fix-1014.js").read_text(encoding="utf-8")
        cls.hub = ROOT.joinpath("static", "admin-course-material.js").read_text(encoding="utf-8")

    def test_finish_wrapper_calls_canonical_navigation_owner(self):
        self.assertIn("return await canonical()", self.runtime)
        self.assertIn("teacherContentStudioClose?.(false)", self.wizard)

    def test_course_creation_verifies_material_links_before_exit(self):
        for marker in (
            "verifyCreatedCourseMaterials",
            "expectedMaterialIds",
            "linksVerified",
            "active:true",
            "避免學員看到 0 份教材",
        ):
            self.assertIn(marker, self.wizard)

    def test_background_completed_material_ids_are_verified(self):
        self.assertIn("rows.map(row=>String(row.materialId||''))", self.wizard)
        self.assertIn("await verifyCreatedCourseMaterials()", self.wizard)

    def test_course_wizard_publishes_only_after_readiness_and_then_returns(self):
        for marker in (
            "courseWizard681PublishAndOpen",
            "publishAndOpenCourseWorkspace",
            "/readiness",
            "action:'mark_ready'",
            "action:'publish'",
            "確認並正式發布",
            "儲存草稿並離開",
            "這一步是唯一正式發布點",
            "publicationBlockerText",
            "publishedCourse.active!==true",
            "課程發布回應未確認為學員可見狀態",
        ):
            self.assertIn(marker, self.wizard)

    def test_orphaned_materials_can_be_relinked_without_reupload(self):
        for marker in (
            "data-material-course-link",
            "歸入課程",
            "更換課程",
            "material-course-link-dialog",
            "儲存教材關聯",
        ):
            self.assertIn(marker, self.hub)
        self.assertIn("body:JSON.stringify({courseId,active:courseId?true", self.hub)


if __name__ == "__main__":
    unittest.main()
