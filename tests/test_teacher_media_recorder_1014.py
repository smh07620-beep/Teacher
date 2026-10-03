from pathlib import Path
import unittest

from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class TeacherMediaRecorder1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "teacher-media-recorder-1014.js").read_text(encoding="utf-8")

    def test_recorder_loads_after_direct_upload_transport(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertIn("/teacher-media-recorder-1014.js", body)
        self.assertLess(body.index("/material-upload-client.js"), body.index("/teacher-media-recorder-1014.js"))

    def test_browser_recording_supports_audio_camera_and_screen(self):
        for marker in (
            "new MediaRecorder",
            "navigator.mediaDevices.getUserMedia",
            "navigator.mediaDevices.getDisplayMedia",
            "🎙️ 開始錄音",
            "🎥 攝影機錄影",
            "🖥️ 螢幕＋旁白",
        ):
            self.assertIn(marker, self.source)

    def test_recording_requires_preview_before_explicit_upload(self):
        self.assertIn("recordedFile = new File", self.source)
        self.assertIn("showRecordedPreview(blob)", self.source)
        self.assertIn("☁️ 上傳成教材", self.source)
        self.assertIn("teacher-record-discard-1014", self.source)

    def test_upload_reuses_browser_to_r2_client(self):
        self.assertIn("window.MaterialUploadClient.enqueue(form", self.source)
        self.assertIn("Browser → R2", self.source)
        self.assertIn("Worker 會繼續處理", self.source)
        self.assertNotIn("fetch('/api/slides/upload", self.source)
        self.assertNotIn("X-Admin-Key", self.source)

    def test_upload_preserves_course_group_and_area_metadata(self):
        for marker in (
            "form.append('group', group)",
            "form.append('area', area)",
            "form.append('courseId', courseId)",
            "form.append('materialType'",
            "/api/courses?area=",
        ):
            self.assertIn(marker, self.source)

    def test_privacy_reminder_is_visible(self):
        self.assertIn("病人姓名", self.source)
        self.assertIn("病歷號", self.source)
        self.assertIn("身分證字號", self.source)
        self.assertIn("不必要個資", self.source)

    def test_leaving_media_workspace_stops_live_capture_resources(self):
        self.assertIn("function stopCaptureForWorkspaceExit()", self.source)
        self.assertIn("stopTimer();", self.source)
        self.assertIn("stopStreams();", self.source)
        self.assertIn("media.classList.contains('hidden')", self.source)
        self.assertIn("attributeFilter: ['class']", self.source)
        self.assertIn("window.addEventListener('pagehide', stopCaptureForWorkspaceExit)", self.source)
        self.assertIn("cleanup: stopCaptureForWorkspaceExit", self.source)

    def test_server_rbac_remains_authoritative(self):
        self.assertIn("has('material.manage')", self.source)
        for forbidden in ("ROLE_PERMISSIONS", "require_permission", "professionalTitle", "responsibilityTags"):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
