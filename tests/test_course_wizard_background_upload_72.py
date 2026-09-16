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

    def test_shared_transport_uses_background_jobs_and_session_cookies(self):
        source = ROOT.joinpath('static', 'material-upload-client.js').read_text(encoding='utf-8')
        self.assertIn("/api/material-jobs/upload", source)
        self.assertIn('xhr.withCredentials=true', source)
        self.assertIn('onProgress', source)
        self.assertIn('response.status', ROOT.joinpath('static', 'course-wizard-681.js').read_text(encoding='utf-8'))

    def test_admin_upload_delegates_to_shared_transport(self):
        source = ROOT.joinpath('static', 'admin-material-upload.js').read_text(encoding='utf-8')
        self.assertIn('MaterialUploadClient.enqueue', source)


if __name__ == '__main__':
    unittest.main()
