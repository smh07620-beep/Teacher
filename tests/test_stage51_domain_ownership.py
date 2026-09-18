import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class Stage51DomainOwnershipTests(unittest.TestCase):
    def test_production_composition_has_no_redundant_stage51_route_replacement(self):
        source = ROOT.joinpath("pgy_app.py").read_text(encoding="utf-8")
        for name in (
            "register_legacy_material_routes",
            "register_legacy_course_routes",
            "register_legacy_assessment_routes",
        ):
            self.assertNotIn(name, source)
        self.assertIn("app = register_rbac_681(legacy_app)", source)

        compatibility_host = ROOT.joinpath("app.py").read_text(encoding="utf-8")
        self.assertIn("canonical_materials.list_materials", compatibility_host)
        self.assertIn("canonical_courses.list_courses", compatibility_host)
        self.assertIn("canonical_assessments.list_categories", compatibility_host)

    def test_courses_service_owns_course_mutation_and_plan_rules(self):
        source = ROOT.joinpath("teacher_app/courses/service.py").read_text(encoding="utf-8")
        for marker in (
            "INSERT INTO courses",
            "UPDATE courses SET",
            "DELETE FROM courses",
            "COURSE_MATERIALS_CHANGED",
            "learningObjectives",
        ):
            self.assertIn(marker, source)

    def test_assessment_service_owns_review_publication_and_material_link_rules(self):
        source = ROOT.joinpath("teacher_app/assessments/service.py").read_text(encoding="utf-8")
        for marker in (
            "INSERT INTO quiz_categories",
            "review_status",
            "quiz_publications",
            "ASSESSMENT_NOT_REVIEWED",
            "materialIds",
        ):
            self.assertIn(marker, source)

    def test_material_service_does_not_import_cloud_credentials_or_sdks(self):
        source = ROOT.joinpath("teacher_app/materials/service.py").read_text(encoding="utf-8")
        self.assertIn("base.gdrive_delete_material", source)
        self.assertIn("base.mega_destroy", source)
        self.assertIn("base.r2_delete_prefix", source)
        self.assertIn("base.oci_delete_prefix", source)
        for forbidden in (
            "boto3",
            "google.oauth2",
            "googleapiclient",
            "R2_SECRET_ACCESS_KEY",
            "GDRIVE_CLIENT_SECRET",
            "GDRIVE_REFRESH_TOKEN",
        ):
            self.assertNotIn(forbidden, source)

    def test_stage51_route_modules_are_response_helpers_not_runtime_replacers(self):
        for path in (
            "teacher_app/materials/routes.py",
            "teacher_app/courses/routes.py",
            "teacher_app/assessments/routes.py",
        ):
            source = ROOT.joinpath(path).read_text(encoding="utf-8")
            self.assertIn("def _legacy_error", source)
            self.assertNotIn("app.view_functions.update", source)
            self.assertNotIn("register_legacy_", source)


if __name__ == "__main__":
    unittest.main()
