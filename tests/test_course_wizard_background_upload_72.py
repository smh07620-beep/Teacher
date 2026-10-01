import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class CourseWizardBackgroundUpload72Tests(unittest.TestCase):
    def test_wizard_uses_shared_background_transport_without_admin_key(self):
        source = ROOT.joinpath('static', 'course-wizard-681.js').read_text(encoding='utf-8')
        self.assertIn('MaterialUploadClient.enqueue', source)
        self.assertIn("form.append('materialType',meta.materialType||'auto')", source)
        self.assertNotIn('X-Admin-Key', source)
        self.assertNotIn('getAdminKey', source)

    def test_shared_transport_keeps_r2_primary_with_guarded_web_fallback(self):
        source = ROOT.joinpath('static', 'material-upload-client.js').read_text(encoding='utf-8')
        self.assertIn("/api/material-upload/init", source)
        self.assertIn("hashStrategy:'sha256-parts-v1'", source)
        self.assertIn('CONCURRENCY=3', source)
        self.assertNotIn('X-Admin-Key', source)
        self.assertNotIn('getAdminKey', source)
        self.assertIn('directUpload(formData,options)', source)
        self.assertIn("/api/material-jobs/upload", source)
        self.assertIn('fallbackToSameOriginQueue', source)
        self.assertIn('COMPAT_QUEUE_FALLBACK_MAX_BYTES=25*1024*1024', source)
        self.assertIn('isDirectNetworkFailure', source)
        self.assertNotIn('XMLHttpRequest', source)
        self.assertIn('onProgress', source)
        self.assertIn('response.status', ROOT.joinpath('static', 'course-wizard-681.js').read_text(encoding='utf-8'))

    def test_wizard_opts_into_network_only_small_file_fallback(self):
        source = ROOT.joinpath('static', 'course-wizard-681.js').read_text(encoding='utf-8')
        self.assertIn('fallbackToSameOriginQueue:true', source)
        self.assertIn('雲端直傳暫時無法連線', source)

    def test_admin_upload_delegates_to_shared_transport(self):
        source = ROOT.joinpath('static', 'admin-material-upload.js').read_text(encoding='utf-8')
        self.assertIn('MaterialUploadClient.enqueue', source)


if __name__ == '__main__':
    unittest.main()
