import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class Stage51DomainOwnershipTests(unittest.TestCase):
    def test_production_composition_registers_canonical_domains_before_rbac(self):
        source = ROOT.joinpath("pgy_app.py").read_text(encoding="utf-8")
        registrations = (
            "register_legacy_material_routes",
            "register_legacy_course_routes",
            "register_legacy_assessment_routes",
        )
        for name in registrations:
            self.assertIn(f"from teacher_app.", source)
            self.assertIn(f"app = {name}(legacy_app)", source)
            self.assertLess(source.index(f"app = {name}(legacy_app)"), source.index("app = register_rbac_681(legacy_app)"))

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

    def test_legacy_url_adapters_replace_only_existing_endpoint_names(self):
        expected = {
            "teacher_app/materials/routes.py": ("api_list_slides", "api_admin_slides", "api_update_slide", "api_delete_slide"),
            "teacher_app/courses/routes.py": ("api_courses", "api_courses_admin", "api_create_course", "api_update_course", "api_delete_course", "api_get_teaching_plan", "api_save_teaching_plan"),
            "teacher_app/assessments/routes.py": ("api_list_quiz_categories", "api_admin_list_quiz_categories", "api_create_quiz_category", "api_update_quiz_category", "api_review_quiz_category", "api_quiz_publications", "api_publish_quiz_category", "api_quiz_category_materials", "api_update_quiz_category_materials", "api_delete_quiz_category"),
        }
        for path, names in expected.items():
            source = ROOT.joinpath(path).read_text(encoding="utf-8")
            self.assertIn("app.view_functions.update(replacements)", source)
            for name in names:
                self.assertIn(f'"{name}"', source)


if __name__ == "__main__":
    unittest.main()
