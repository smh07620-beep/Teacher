import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class Phase3AdminMaterialsTests(unittest.TestCase):
    def test_materials_module_loads_after_system_override(self):
        frontend = ROOT.joinpath('pgy_frontend.py').read_text(encoding='utf-8')
        system_pos = frontend.index('/admin-system.js?v=7104')
        materials_pos = frontend.index('/admin-materials.js?v=7105')
        self.assertLess(system_pos, materials_pos)

    def test_materials_module_preserves_global_contracts(self):
        source = ROOT.joinpath('static/admin-materials.js').read_text(encoding='utf-8')
        for name in (
            'invalidateAdminMaterialsCache',
            'fetchAdminMaterials',
            'renderAdminMaterials',
            'hydrateMaterialIndexStatus',
            'rebuildMaterialIndex',
            'formatFileBytes',
        ):
            self.assertIn(f'window.{name}', source)
        self.assertIn('/api/slides/admin', source)
        self.assertIn('/api/material-search/${encodeURIComponent(m.id)}/status', source)
        self.assertIn('/api/material-search/${encodeURIComponent(id)}/index', source)

    def test_materials_module_keeps_existing_security_and_rbac_boundary(self):
        source = ROOT.joinpath('static/admin-materials.js').read_text(encoding='utf-8')
        self.assertIn('getAdminKey', source)
        self.assertIn('X-Admin-Key', source)
        self.assertNotIn('professional_title', source)
        self.assertNotIn('responsibility_tags', source)
        self.assertNotIn('localStorage.setItem', source)
        self.assertNotIn('sessionStorage.setItem', source)


if __name__ == '__main__':
    unittest.main()
