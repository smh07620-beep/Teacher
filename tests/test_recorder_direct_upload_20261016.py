"""Teacher-recorded video/audio must go browser -> R2 directly, never through Render."""
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"


class RecorderDirectUploadTests(unittest.TestCase):
    def test_recorder_uses_direct_upload_client_without_same_origin_fallback(self):
        src = (STATIC / "teacher-media-recorder-1014.js").read_text(encoding="utf-8")
        self.assertIn("MaterialUploadClient.enqueue", src)
        self.assertNotIn("fallbackToSameOriginQueue", src)
        self.assertNotIn("/api/material-jobs/upload", src)

    def test_client_tries_presigned_direct_upload_first(self):
        src = (STATIC / "material-upload-client.js").read_text(encoding="utf-8")
        self.assertIn("return await directUpload(formData,options)", src)


if __name__ == "__main__":
    unittest.main()
