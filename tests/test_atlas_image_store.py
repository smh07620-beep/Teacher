"""Behavioral coverage for canonical Atlas local-image storage."""
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from teacher_app.atlas import image_store


class AtlasImageStoreTests(unittest.TestCase):
    def png_bytes(self, size=(16, 12)):
        output = BytesIO()
        Image.new("RGB", size, "white").save(output, format="PNG")
        return output.getvalue()

    def test_valid_image_creates_original_and_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp:
            stored = image_store.store_image_bytes(tmp, self.png_bytes(), "cell.png")
            directory = Path(tmp) / "atlas_images"
            self.assertTrue(directory.joinpath(stored["name"]).is_file())
            self.assertTrue(directory.joinpath("thumb-" + stored["name"]).is_file())
            self.assertEqual(stored["imageUrl"], f'/api/atlas/images/{stored["name"]}')
            self.assertEqual(stored["thumbnailUrl"], f'/api/atlas/images/thumb-{stored["name"]}')

    def test_invalid_extension_or_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(image_store.AtlasImageError):
                image_store.store_image_bytes(tmp, self.png_bytes(), "cell.exe")
            with self.assertRaises(image_store.AtlasImageError):
                image_store.store_image_bytes(tmp, b"not-an-image", "cell.png")

    def test_manual_upload_size_budget_and_docx_unbounded_mode_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = self.png_bytes()
            with self.assertRaises(image_store.AtlasImageError):
                image_store.store_image_bytes(tmp, raw, ".png", max_bytes=1)
            stored = image_store.store_image_bytes(tmp, raw, ".png", max_bytes=None)
            self.assertTrue(stored["name"].endswith(".png"))

    def test_requested_image_normalizes_thumbnail_to_original_visibility_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory, safe, image_url = image_store.requested_image(tmp, "thumb-cell.png")
            self.assertEqual(directory, Path(tmp) / "atlas_images")
            self.assertEqual(safe, "thumb-cell.png")
            self.assertEqual(image_url, "/api/atlas/images/cell.png")


if __name__ == "__main__":
    unittest.main()
