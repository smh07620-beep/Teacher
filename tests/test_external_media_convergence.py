import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

from teacher_app.materials.external_media_routes import register_external_media


ROOT = Path(__file__).parents[1]


class ExternalMediaConvergenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = ROOT.joinpath("teacher_app/materials/external_media_routes.py").read_text(encoding="utf-8")
        cls.root_alias = ROOT.joinpath("external_media_68.py").read_text(encoding="utf-8")
        cls.service = ROOT.joinpath("teacher_app/materials/external_media.py").read_text(encoding="utf-8")

    def test_root_adapter_keeps_http_and_permissions_only(self):
        self.assertIn("register_external_media", self.adapter)
        self.assertIn('scope_filter.require_permission(owner, "material.manage")', self.adapter)
        self.assertIn("scope_filter.scoped(", self.adapter)
        self.assertIn("external_media_service.set_external_media", self.adapter)
        self.assertIn("external_media_service.create_external_material", self.adapter)
        self.assertIn("external_media_service.get_external_media", self.adapter)
        self.assertNotIn("base.", self.adapter)
        self.assertNotIn("require_admin", self.adapter)

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
        self.assertIn("validate_external_url = external_media_service.validate_external_url", self.adapter)
        self.assertIn("teacher_app.materials", self.root_alias)
        self.assertIn("sys.modules[__name__] = _routes", self.root_alias)

    def test_registration_accepts_flask_app_and_uses_request_bound_actor(self):
        app = Flask("direct-external-media")
        app.config.update(TESTING=True, DIRECT_MEDIA_ALLOWLIST=[])

        @app.before_request
        def bind_actor():
            g.teacher_user = {"username": "root", "role": "system_admin"}

        register_external_media(app)
        client = app.test_client()
        result = {
            "material": {"id": "external-1", "storageBackend": "external"},
            "externalMedia": {"provider": "youtube", "canonicalUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "videoId": "dQw4w9WgXcQ"},
        }
        with patch(
            "teacher_app.materials.external_media_routes.external_media_service.create_external_material",
            return_value=result,
        ):
            response = client.post(
                "/api/materials/external",
                json={"title": "Video", "group": "grpBio", "url": "https://youtu.be/dQw4w9WgXcQ"},
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["externalMedia"]["provider"], "youtube")


if __name__ == "__main__":
    unittest.main()
