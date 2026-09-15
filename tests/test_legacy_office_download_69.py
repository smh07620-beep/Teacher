import unittest
from pathlib import Path

from flask import Flask, jsonify

from legacy_office_69 import register_legacy_office_69


ROOT = Path(__file__).parents[1]


class FakeBase:
    DEFAULT_GROUP = "grpBio"

    def __init__(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="legacy-office-test")
        self.allowed_group = "grpHema"
        self.original_calls = []
        self.materials = {
            "single": {
                "id": "single",
                "active": True,
                "filename": "lesson.pptx",
                "group": "grpHema",
                "storageMeta": {"previewMode": "single_pdf", "previewFilename": "preview.pdf"},
            },
            "paged": {
                "id": "paged",
                "active": True,
                "filename": "manual.docx",
                "group": "grpHema",
                "viewerMode": "slides",
                "pageCount": 8,
                "storageMeta": {},
            },
            "other-group": {
                "id": "other-group",
                "active": True,
                "filename": "other.xlsx",
                "group": "grpBio",
                "storageMeta": {"previewMode": "single_pdf"},
            },
            "pdf": {
                "id": "pdf",
                "active": True,
                "filename": "reference.pdf",
                "group": "grpHema",
                "storageMeta": {},
            },
        }

        @self.app.get("/download/<slide_id>")
        def download_slide(slide_id):
            self.original_calls.append(slide_id)
            return f"ORIGINAL:{slide_id}"

    def get_material(self, material_id):
        return self.materials.get(material_id)

    def require_scoped_permission(self, permission, group=None):
        if permission != "material.manage" or group != self.allowed_group:
            return jsonify({"error": "此資源不在你的授權範圍。"}), 403
        return None

    def require_admin(self):
        return jsonify({"error": "legacy guard should not be needed"}), 403


class LegacyOfficeDownload69Tests(unittest.TestCase):
    def setUp(self):
        self.base = FakeBase()
        register_legacy_office_69(self.base)
        self.client = self.base.app.test_client()

    def test_single_pdf_office_source_redirects_to_preview(self):
        response = self.client.get("/download/single")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/material-preview/single"))
        self.assertEqual(self.base.original_calls, [])

    def test_page_based_office_never_falls_through_to_source(self):
        response = self.client.get("/download/paged")
        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertTrue(payload["previewRequired"])
        self.assertEqual(payload["materialId"], "paged")
        self.assertIn("Office 原始檔下載已停用", payload["error"])
        self.assertEqual(self.base.original_calls, [])

    def test_cross_group_office_download_is_denied_before_preview(self):
        response = self.client.get("/download/other-group")
        self.assertEqual(response.status_code, 403)
        self.assertIn("授權範圍", response.get_json()["error"])
        self.assertEqual(self.base.original_calls, [])

    def test_non_office_legacy_download_keeps_existing_behavior(self):
        response = self.client.get("/download/pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "ORIGINAL:pdf")
        self.assertEqual(self.base.original_calls, ["pdf"])

    def test_missing_material_is_404(self):
        response = self.client.get("/download/missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.base.original_calls, [])

    def test_adapter_is_registered_after_rbac_in_deployment_entrypoint(self):
        source = ROOT.joinpath("pgy_app.py").read_text(encoding="utf-8")
        self.assertIn("from legacy_office_69 import register_legacy_office_69", source)
        self.assertLess(source.index("register_rbac_681(legacy_app)"), source.index("register_legacy_office_69(legacy_app)"))


if __name__ == "__main__":
    unittest.main()
