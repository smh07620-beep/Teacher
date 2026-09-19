import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class Stage51DomainOwnershipTests(unittest.TestCase):
    def test_production_composition_has_no_redundant_stage51_route_replacement(self):
        source = ROOT.joinpath("teacher_app/factory.py").read_text(encoding="utf-8")
        for name in (
            "register_legacy_material_routes",
            "register_legacy_course_routes",
            "register_legacy_assessment_routes",
        ):
            self.assertNotIn(name, source)
        self.assertIn("app = register_rbac_681(app)", source)

        compatibility_host = ROOT.joinpath("teacher_app/legacy_host.py").read_text(encoding="utf-8")
        self.assertIn("canonical_materials.list_materials", compatibility_host)
        self.assertIn("canonical_courses.list_courses", compatibility_host)
        self.assertIn("canonical_assessments.list_categories", compatibility_host)

    def test_courses_repository_owns_sql_and_service_owns_rules(self):
        service = ROOT.joinpath("teacher_app/courses/service.py").read_text(encoding="utf-8")
        repository = ROOT.joinpath("teacher_app/courses/repository.py").read_text(encoding="utf-8")
        for marker in (
            "INSERT INTO courses",
            "UPDATE courses SET",
            "DELETE FROM courses",
        ):
            self.assertIn(marker, repository)
            self.assertNotIn(marker, service)
        for marker in (
            "COURSE_MATERIALS_CHANGED",
            "learningObjectives",
            "repository.create_course",
            "repository.update_course",
        ):
            self.assertIn(marker, service)

    def test_assessment_repository_owns_sql_and_service_owns_workflow_rules(self):
        service = ROOT.joinpath("teacher_app/assessments/service.py").read_text(encoding="utf-8")
        repository = ROOT.joinpath("teacher_app/assessments/repository.py").read_text(encoding="utf-8")
        for marker in (
            "INSERT INTO quiz_categories",
            "review_status",
            "quiz_publications",
        ):
            self.assertIn(marker, repository)
        for marker in (
            "ASSESSMENT_NOT_REVIEWED",
            "materialIds",
            "repository.publish_category",
        ):
            self.assertIn(marker, service)
        for sql in ("INSERT INTO quiz_categories", "UPDATE quiz_categories SET", "INSERT INTO quiz_publications"):
            self.assertNotIn(sql, service)

    def test_material_service_does_not_import_cloud_credentials_or_sdks(self):
        source = ROOT.joinpath("teacher_app/materials/service.py").read_text(encoding="utf-8")
        self.assertIn("canonical_storage.delete_strict", source)
        self.assertIn("base.storage_delete_adapters", source)
        for retired in ("base.gdrive_delete_material", "base.mega_destroy", "base.r2_delete_prefix", "base.oci_delete_prefix"):
            self.assertNotIn(retired, source)
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
