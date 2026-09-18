import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ExternalMediaConvergenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = ROOT.joinpath("external_media_68.py").read_text(encoding="utf-8")
        cls.service = ROOT.joinpath("teacher_app/materials/external_media.py").read_text(encoding="utf-8")

    def test_root_adapter_keeps_http_and_permissions_only(self):
        self.assertIn("register_external_media", self.adapter)
        self.assertIn('base.require_permission("material.manage")', self.adapter)
        self.assertIn("base.require_scoped_permission", self.adapter)
        self.assertIn("external_media_service.set_external_media", self.adapter)
        self.assertIn("external_media_service.create_external_material", self.adapter)
        self.assertIn("external_media_service.get_external_media", self.adapter)

        for forbidden in (
            "urlparse(",
            "ipaddress.ip_address",
            "uuid.uuid4",
            "json.dumps",
            "INSERT INTO external_media",
            "SELECT provider,canonical_url,video_id",
            "insert_material_on_connection",
        ):
            self.assertNotIn(forbidden, self.adapter)

    def test_canonical_service_owns_validation_and_persistence(self):
        for marker in (
            "def validate_external_url(",
            "def set_external_media(",
            "def create_external_material(",
            "def get_external_media(",
            "course_repository.get_course",
            "assessment_repository.get_category",
            "material_repository.insert_material_on_connection",
            "material_repository.get_material",
            "common_db.transaction()",
            "common_db.read_connection()",
        ):
            self.assertIn(marker, self.service)

    def test_canonical_service_has_no_flask_or_legacy_base_dependency(self):
        self.assertNotIn("from flask", self.service)
        self.assertNotIn("base.", self.service)
        self.assertNotIn("require_permission", self.service)
        self.assertNotIn("require_admin", self.service)

    def test_root_keeps_legacy_validator_export(self):
        self.assertIn(
            "validate_external_url = external_media_service.validate_external_url",
            self.adapter,
        )


if __name__ == "__main__":
    unittest.main()
