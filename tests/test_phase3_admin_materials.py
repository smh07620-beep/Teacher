import unittest
from pathlib import Path

from pgy_frontend import ASSET_MANIFEST

ROOT = Path(__file__).parents[1]


class Phase3AdminMaterialsTests(unittest.TestCase):
    def test_materials_module_loads_after_system_override(self):
        body = ASSET_MANIFEST["system"]["body"]
        system_pos = body.index('/admin-system.js')
        materials_pos = body.index('/admin-materials.js')
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

    def test_material_list_ignores_stale_concurrent_responses(self):
        materials = ROOT.joinpath('static/admin-materials.js').read_text(encoding='utf-8')
        self.assertIn('adminMaterialsRequestGeneration', materials)
        self.assertIn('generation === adminMaterialsRequestGeneration', materials)
        self.assertIn('An older response must never replace a newer completed material list', materials)
        stale_branch = materials[materials.index('An older response must never replace a newer completed material list'):]
        self.assertIn('return list;', stale_branch[:900])
        self.assertNotIn('return Array.isArray(adminMaterialsCache.data) ? adminMaterialsCache.data : list;', stale_branch[:900])

    def test_materials_fetch_has_one_canonical_owner(self):
        materials = ROOT.joinpath('static/admin-materials.js').read_text(encoding='utf-8')
        rbac = ROOT.joinpath('static/rbac-ui-681.js').read_text(encoding='utf-8')
        self.assertIn('window.fetchAdminMaterials = async function', materials)
        self.assertIn("res.status === 401", materials)
        self.assertIn("location.href = `/login?next=${next}`", materials)
        self.assertIn("res.status === 403", materials)
        self.assertNotIn('window.fetchAdminMaterials =', rbac)
        self.assertIn('Material list fetching is owned by admin-materials.js', rbac)

    def test_materials_module_keeps_existing_security_and_rbac_boundary(self):
        source = ROOT.joinpath('static/admin-materials.js').read_text(encoding='utf-8')
        self.assertNotIn('getAdminKey', source)
        self.assertNotIn('X-Admin-Key', source)
        self.assertIn("credentials:'same-origin'", source)
        self.assertNotIn('professional_title', source)
        self.assertNotIn('responsibility_tags', source)
        self.assertNotIn('localStorage.setItem', source)
        self.assertNotIn('sessionStorage.setItem', source)


if __name__ == '__main__':
    unittest.main()
