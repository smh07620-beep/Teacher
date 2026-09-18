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
            'editAdminMaterial',
            'toggleAdminMaterial',
            'deleteAdminMaterial',
        ):
            self.assertIn(f'window.{name}', source)
        self.assertIn('MaterialUploadClient.enqueue', source)
        self.assertIn('/api/material-upload/init', source)
        self.assertIn('/complete', source)
        self.assertIn('/api/slides/${id}', source)

    def test_upload_module_keeps_server_authorization_boundary(self):
        source = ROOT.joinpath('static/admin-material-upload.js').read_text(encoding='utf-8')
        self.assertIn('getAdminKey', source)
        self.assertIn('X-Admin-Key', source)
        self.assertNotIn('professional_title', source)
        self.assertNotIn('responsibility_tags', source)
        self.assertNotIn('localStorage.setItem', source)
        self.assertNotIn('sessionStorage.setItem', source)

    def test_large_file_path_keeps_sha256_and_multipart_contract(self):
        source = ROOT.joinpath('static/admin-material-upload.js').read_text(encoding='utf-8')
        self.assertIn("crypto.subtle.digest('SHA-256'", source)
        self.assertIn('250*1024*1024', source)
        self.assertIn('partNumber', source)
        self.assertIn("res.headers.get('etag')", source)


if __name__ == '__main__':
    unittest.main()
