import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from teacher_app.atlas import importer


class AtlasImporterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.slides = self.root / "slides"
        self.storage = self.root / "storage"
        self.material_id = "docx-1"
        self.source_dir = self.slides / self.material_id
        self.source_dir.mkdir(parents=True)
        self.docx = self.source_dir / "atlas.docx"
        out = BytesIO()
        Image.new("RGB", (2, 2), "white").save(out, format="PNG")
        self.png = out.getvalue()
        self.material = {
            "id": self.material_id,
            "group": "grpHema",
            "folder": self.material_id,
            "storageFilename": "atlas.docx",
            "filename": "atlas.docx",
        }
        self.user = {"username": "teacher"}

    def write_docx(self, *, include_document=True, image_count=2):
        document = (
            '<w:document xmlns:w="w" xmlns:r="r"><w:body>'
            '<w:p><w:r><w:t>morphology context</w:t></w:r></w:p>'
            '<a:blip r:embed="rId1"/><a:blip r:embed="rId2"/>'
            '</w:body></w:document>'
        )
        with zipfile.ZipFile(self.docx, "w") as archive:
            if include_document:
                archive.writestr("word/document.xml", document)
            for index in range(1, image_count + 1):
                archive.writestr(f"word/media/image{index}.png", self.png)

    def test_preview_preserves_established_projection_and_warning(self):
        self.write_docx()
        with patch.object(importer.material_repository, "get_material", return_value=self.material), patch.object(importer.service, "can_manage", return_value=True):
            payload = importer.preview_import(self.user, self.material_id, self.slides)
        self.assertEqual(payload["materialId"], self.material_id)
        self.assertEqual(payload["defaultGroup"], "grpHema")
        self.assertEqual(payload["initialStatus"], "draft")
        self.assertEqual([item["relationshipId"] for item in payload["preview"]["images"]], ["rId1", "rId2"])
        self.assertIn(importer.PREVIEW_WARNING, payload["preview"]["warnings"])

    def test_confirm_merges_common_metadata_and_per_image_override(self):
        self.write_docx()
        body = {
            "metadata": {
                "title": "Shared title",
                "group": "grpHema",
                "category": "blood_cell",
                "description": "Shared description",
                "tags": ["shared"],
                "differentialPoints": "Shared differential",
                "teachingNotes": "Shared notes",
                "difficulty": "basic",
                "sortOrder": 3,
            },
            "items": [
                {"index": 1},
                {"index": 2, "title": "Override title", "tags": ["override"], "sortOrder": 9},
            ],
        }
        created_payloads = []

        def create_item(_user, values):
            created_payloads.append(values)
            return f"atlas-{len(created_payloads)}"

        with patch.object(importer.material_repository, "get_material", return_value=self.material), patch.object(importer.service, "can_manage", return_value=True), patch.object(importer.service, "create_item", side_effect=create_item):
            result = importer.confirm_import(
                self.user,
                self.material_id,
                body,
                uploaded_slides_dir=self.slides,
                material_storage=self.storage,
            )

        self.assertEqual(result, {"ok": True, "created": ["atlas-1", "atlas-2"], "status": "draft"})
        self.assertEqual([item["title"] for item in created_payloads], ["Shared title", "Override title"])
        self.assertEqual(created_payloads[0]["tags"], ["shared"])
        self.assertEqual(created_payloads[1]["tags"], ["override"])
        self.assertTrue(all(item["source"] == "docx" and not item["published"] for item in created_payloads))
        self.assertTrue(all(item["sourceMaterialId"] == self.material_id for item in created_payloads))
        self.assertTrue(all(str(item["imageUrl"]).startswith("/api/atlas/images/") for item in created_payloads))

    def test_canonical_material_lookup_precedes_legacy_fallback(self):
        self.write_docx()
        legacy_calls = []
        with patch.object(importer.material_repository, "get_material", return_value=self.material):
            material, path = importer.docx_source(
                self.material_id,
                self.slides,
                legacy_material_getter=lambda material_id: legacy_calls.append(material_id),
            )
        self.assertEqual(material["id"], self.material_id)
        self.assertEqual(path, self.docx)
        self.assertEqual(legacy_calls, [])


if __name__ == "__main__":
    unittest.main()
