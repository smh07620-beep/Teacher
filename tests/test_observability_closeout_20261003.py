import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, jsonify

from teacher_app.common import privacy
from teacher_app.config import StoragePaths
from teacher_app.materials.upload_progress import UploadProgressStore


def _paths(root: Path) -> StoragePaths:
    material = root / "materials"
    return StoragePaths(
        base_dir=root,
        static_dir=root / "static",
        slides_dir=root / "static" / "slides",
        material_storage=material,
        upload_dir=material / "ppt",
        question_images_dir=material / "question_images",
        uploaded_slides_dir=material / "slides",
        doc_templates_dir=material / "doc_templates",
        pgy_assessment_templates_dir=material / "pgy_assessment_templates",
        data_dir=root / "data",
        tmp_dir=root / "tmp",
        upload_progress_dir=root / "tmp" / "upload_progress",
        preview_cache_dir=root / "tmp" / "preview_cache",
    )


class ObservabilityCloseout20261003Tests(unittest.TestCase):
    def test_privacy_material_lookup_failure_fails_closed_without_secret_log(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="privacy-test")

        def unavailable(_material_id):
            raise RuntimeError("password=do-not-log")

        with patch.object(privacy, "install_extractor_wrappers", return_value=0):
            privacy.register_ai_privacy(app, material_lookup=unavailable)

        @app.post("/api/ai-questions/generate")
        def generate():
            return jsonify({"ok": True})

        with patch.dict(
            os.environ,
            {"AI_EXTERNAL_PROCESSING_ENABLED": "true", "AI_EXTERNAL_MEDIA_ALLOWED": "false"},
            clear=False,
        ):
            with self.assertLogs("teacher_app.common.privacy", level="WARNING") as captured:
                response = app.test_client().post(
                    "/api/ai-questions/generate",
                    json={"materialId": "mat-1"},
                )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["code"], "AI_PRIVACY_LOOKUP_UNAVAILABLE")
        rendered = "\n".join(captured.output)
        self.assertIn("AI privacy material lookup failed", rendered)
        self.assertIn("RuntimeError", rendered)
        self.assertNotIn("do-not-log", rendered)

    def test_progress_write_failure_is_best_effort_but_logged_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            store = UploadProgressStore(_paths(Path(temp)))
            with patch.object(Path, "write_text", side_effect=RuntimeError("token=do-not-log")):
                with self.assertLogs("teacher_app.materials.upload_progress", level="WARNING") as captured:
                    store.set("progress-1", 50, "處理中")

        rendered = "\n".join(captured.output)
        self.assertIn("material upload progress write failed", rendered)
        self.assertIn("RuntimeError", rendered)
        self.assertNotIn("do-not-log", rendered)


if __name__ == "__main__":
    unittest.main()
