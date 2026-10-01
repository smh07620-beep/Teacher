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

    def test_course_wizard_forces_direct_r2_and_surfaces_progress(self):
        source = ROOT.joinpath('static', 'course-wizard-681.js').read_text(encoding='utf-8')
        self.assertIn('fallbackToSameOriginQueue:false', source)
        self.assertNotIn('fallbackToSameOriginQueue:true', source)
        self.assertIn('上傳至 R2', source)
        self.assertIn('/api/material-jobs/${encodeURIComponent(id)}', source)
        self.assertIn('背景教材處理中', source)
        self.assertIn('row.error||row.detail', source)

    def test_successful_course_creation_is_locked_and_has_finish_action(self):
        source = ROOT.joinpath('static', 'course-wizard-681.js').read_text(encoding='utf-8')
        self.assertIn('state.created=true', source)
        self.assertIn('完成／返回教材與課程', source)
        self.assertIn('課程已鎖定完成，不會因再次點擊而重複建立', source)
        self.assertIn("if(state.created)return retryFailedUploads();", source)
        self.assertIn('重試未完成教材', source)

    def test_admin_upload_delegates_to_shared_transport(self):
        source = ROOT.joinpath('static', 'admin-material-upload.js').read_text(encoding='utf-8')
        self.assertIn('MaterialUploadClient.enqueue', source)


if __name__ == '__main__':
    unittest.main()
