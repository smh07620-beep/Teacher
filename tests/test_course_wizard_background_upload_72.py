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
        self.assertIn('averageCompletedDurationSeconds', source)
        self.assertIn('progressPercent', source)
        self.assertIn('依 Worker 真實回報階段顯示', source)
        self.assertIn('處理進度', source)
        self.assertIn('COURSE_UPLOAD_PHASES', source)
        self.assertIn('R2 接收', source)
        self.assertIn('下載／驗證', source)
        self.assertIn('轉檔／預覽', source)
        self.assertIn('正式發布', source)

    def test_successful_course_creation_waits_for_material_completion_before_finish(self):
        source = ROOT.joinpath('static', 'course-wizard-681.js').read_text(encoding='utf-8')
        self.assertIn('state.created=true', source)
        self.assertIn('canLeaveCourse()', source)
        self.assertIn('儲存草稿並離開', source)
        self.assertIn('等待教材正式完成後才能離開', source)
        self.assertIn('新教材必須全部顯示「已完成」後', source)
        self.assertIn('beforeunload', source)
        self.assertIn('課程本身已鎖定完成，不會重複建立', source)
        self.assertIn('只有第 4 步發布檢查通過後才會讓學員看見', source)
        self.assertIn("if(state.created){if(state.failedUploads.length)await retryFailedUploads();return state.created;}", source)
        self.assertIn('重試未完成教材', source)
        self.assertIn("window.teacherContentStudioClose?.(false)", source)
        self.assertIn("window.courseWizard681HasPending", source)
        self.assertIn("window.courseWizard681PendingMessage", source)
        self.assertIn("clearWorkflowId();", source)
        self.assertIn("window.AppWorkspaceRoutes.show('course-materials',true)", source)

    def test_completed_course_materials_show_resolved_type_and_docx_atlas_offer(self):
        source = ROOT.joinpath('static', 'course-wizard-681.js').read_text(encoding='utf-8')
        for marker in (
            'hydrateCompletedMaterialInsights',
            'uploadAnalysis',
            '教材自動歸類結果',
            '/api/atlas/import-docx/',
            '檢視並建立 Atlas 草稿',
            "openAtlasDocxWizard('cw681-atlas-import',id)",
        ):
            self.assertIn(marker, source)

    def test_admin_upload_delegates_to_shared_transport(self):
        source = ROOT.joinpath('static', 'admin-material-upload.js').read_text(encoding='utf-8')
        self.assertIn('MaterialUploadClient.enqueue', source)


if __name__ == '__main__':
    unittest.main()
