import shutil
import subprocess
import unittest
from pathlib import Path

from pgy_frontend import ASSET_MANIFEST

ROOT = Path(__file__).parents[1]


class Phase3AdminMaterialUploadTests(unittest.TestCase):
    def test_upload_module_loads_after_jobs_override(self):
        body = ASSET_MANIFEST["system"]["body"]
        jobs_pos = body.index('/admin-jobs.js')
        upload_pos = body.index('/admin-material-upload.js')
        self.assertLess(jobs_pos, upload_pos)

    def test_upload_module_preserves_global_contracts(self):
        source = ROOT.joinpath('static/admin-material-upload.js').read_text(encoding='utf-8')
        for name in (
            'updateAdminMaterialTypeFields',
            'uploadAdminMaterialRequest',
            'sha256File',
            'directR2MaterialUpload',
            'adminUploadMaterials',
            'waitForAdminMaterialJobs',
            'editAdminMaterial',
            'toggleAdminMaterial',
            'deleteAdminMaterial',
        ):
            self.assertIn(f'window.{name}', source)
        self.assertIn('MaterialUploadClient.enqueue', source)
        self.assertIn('MaterialUploadClient.directUpload', source)
        self.assertIn('/api/slides/${id}', source)

    def test_upload_module_keeps_server_authorization_boundary(self):
        source = ROOT.joinpath('static/admin-material-upload.js').read_text(encoding='utf-8')
        self.assertNotIn('getAdminKey', source)
        self.assertNotIn('X-Admin-Key', source)
        self.assertNotIn('professional_title', source)
        self.assertNotIn('responsibility_tags', source)
        self.assertNotIn('localStorage.setItem', source)
        self.assertNotIn('sessionStorage.setItem', source)

    def test_shared_transport_honors_server_single_or_multipart_mode(self):
        source = ROOT.joinpath('static/material-upload-client.js').read_text(encoding='utf-8')
        self.assertIn("crypto.subtle.digest('SHA-256'", source)
        self.assertNotIn('file.arrayBuffer()', source)
        self.assertIn("blob.stream().getReader()", source)
        self.assertIn("await reader.read()", source)
        self.assertIn("hashStrategy:'sha256-parts-v1'", source)
        self.assertIn("FINGERPRINT_STRATEGY='sha256-part-tree-v1'", source)
        self.assertIn("RESUME_STORAGE_KEY='teacher.materialUpload.multipart.v1'", source)
        self.assertIn('/resume', source)
        self.assertIn('uploadedParts', source)
        self.assertIn('localStorage.setItem(RESUME_STORAGE_KEY', source)
        self.assertIn('localStorage.removeItem(RESUME_STORAGE_KEY)', source)
        self.assertIn("session.mode==='single'", source)
        self.assertIn("session.mode==='multipart'", source)
        self.assertIn('singlePutMaxBytes', source)
        self.assertIn('sha256Blob(file)', source)
        self.assertIn('file.slice(start,end)', source)
        self.assertIn('CONCURRENCY=3', source)
        self.assertIn('Promise.all(', source)
        self.assertIn('partNumber', source)
        self.assertIn("response.headers.get('etag')||''", source)
        self.assertIn('await retryPut(part.url,chunk,part.headers||undefined);', source)
        self.assertNotIn('completed[index]', source)
        self.assertNotIn('32*1024*1024', source)
        persisted = source[source.index('function saveResume'):source.index('function findResume')]
        self.assertNotIn('etag', persisted.lower())
        self.assertIn('/api/material-jobs/upload', source)
        self.assertIn('COMPAT_QUEUE_FALLBACK_MAX_BYTES=25*1024*1024', source)
        self.assertIn('fallbackToSameOriginQueue', source)
        self.assertNotIn('R2 未回傳 ETag', source)
        self.assertNotIn('cors exposeheaders', source.lower())
        self.assertNotIn('XMLHttpRequest', source)

    def test_streaming_sha256_matches_node_reference_for_multi_chunk_blob(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node is unavailable')
        source = ROOT.joinpath('static/material-upload-client.js')
        script = r"""
global.window = { crypto: require('crypto').webcrypto };
global.crypto = global.window.crypto;
require(process.argv[1]);
const cryptoNode = require('crypto');
(async () => {
  const bytes = Buffer.alloc(2 * 1024 * 1024 + 123);
  for (let i = 0; i < bytes.length; i += 1) bytes[i] = i % 251;
  const expected = cryptoNode.createHash('sha256').update(bytes).digest('hex');
  const actual = await window.MaterialUploadClient.sha256Blob(new Blob([bytes]));
  if (actual !== expected) {
    console.error(`${actual} != ${expected}`);
    process.exit(2);
  }
})().catch(error => { console.error(error); process.exit(3); });
"""
        result = subprocess.run(
            [node, '-e', script, str(source)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_admin_delegates_transport_mode_to_shared_client(self):
        source = ROOT.joinpath('static/admin-material-upload.js').read_text(encoding='utf-8')
        self.assertIn('MaterialUploadClient.enqueue', source)
        self.assertIn('MaterialUploadClient.directUpload', source)
        self.assertIn('fallbackToSameOriginQueue:true', source)
        self.assertIn('onFallback', source)
        self.assertNotIn('DIRECT_UPLOAD_THRESHOLD', source)
        self.assertNotIn("fetch('/api/material-upload/init'", source)
        self.assertNotIn('DIRECT_VIDEO_EXT', source)

    def test_upload_waits_for_formal_worker_completion_before_allowing_teacher_to_leave(self):
        source = ROOT.joinpath('static/admin-material-upload.js').read_text(encoding='utf-8')
        for marker in (
            "window.addEventListener('beforeunload',materialUploadLeaveGuard)",
            "window.waitForAdminMaterialJobs",
            "/api/material-jobs/'+encodeURIComponent(id)",
            "protocolCompatible===false",
            "請等到全部教材顯示「已完成」再離開",
            "R2 接收完成不等於教材已完成",
            "已正式完成並寫入教材清單",
            "現在可以安全離開或返回課程",
            "R2 原始檔仍保留，可直接重新處理",
            "window.isTeacherMaterialUploadPending",
            "MATERIAL_UPLOAD_PHASES",
            "R2 接收",
            "下載／驗證",
            "轉檔／預覽",
            "正式發布",
        ):
            self.assertIn(marker, source)
        self.assertNotIn('現在可切換頁面或關閉後台視窗，工作會繼續', source)
        self.assertNotIn('你可以離開此頁；完成後會自動出現在教材清單', source)

    def test_direct_upload_keeps_atlas_metadata_fields(self):
        source = ROOT.joinpath('static/admin-material-upload.js').read_text(encoding='utf-8')
        for field in (
            'atlasCategory', 'atlasMagnification', 'atlasInterpretation',
            'atlasClinical', 'atlasDifferential', 'atlasNormality', 'atlasTags',
        ):
            self.assertIn(f"fd.append('{field}'", source)


if __name__ == '__main__':
    unittest.main()
