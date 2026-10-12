"""Atlas images survive a host disk wipe (Render free redeploys clear /tmp)."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from teacher_app.atlas import image_store


class FakeClient:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, **kw):
        self.objects[Key] = Body

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://r2.example/{Params['Key']}?sig=1"


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, format="PNG")
    return buf.getvalue()


class AtlasImageDurabilityTests(unittest.TestCase):
    def test_stored_image_and_thumbnail_are_mirrored_and_recoverable(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.object(image_store, "_object_store", return_value=(client, "bucket")):
            stored = image_store.store_image_bytes(root, _png(), ".png")
            name = stored["name"]
            self.assertIn("atlas-images/" + name, client.objects)
            self.assertIn("atlas-images/thumb-" + name, client.objects)
            for f in Path(root, "atlas_images").iterdir():  # simulate redeploy wipe
                f.unlink()
            self.assertEqual(image_store.object_store_url(name), f"https://r2.example/atlas-images/{name}?sig=1")

    def test_without_object_store_nothing_breaks(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(image_store, "_object_store", return_value=None):
            stored = image_store.store_image_bytes(root, _png(), ".png")
            self.assertTrue(Path(root, "atlas_images", stored["name"]).is_file())
            self.assertEqual(image_store.object_store_url(stored["name"]), "")

    def test_mirror_failure_does_not_fail_the_upload(self):
        client = FakeClient()
        client.put_object = mock.Mock(side_effect=RuntimeError("r2 down"))
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.object(image_store, "_object_store", return_value=(client, "bucket")):
            stored = image_store.store_image_bytes(root, _png(), ".png")
            self.assertTrue(Path(root, "atlas_images", stored["name"]).is_file())


if __name__ == "__main__":
    unittest.main()
