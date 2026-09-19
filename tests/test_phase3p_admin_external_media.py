from pathlib import Path
import unittest

from pgy_frontend import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class Phase3PAdminExternalMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "admin-external-media.js").read_text(encoding="utf-8")
        cls.frontend = (ROOT / "pgy_frontend.py").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github" / "workflows" / "phase3-pgy-checks.yml").read_text(encoding="utf-8")

    def test_preserves_external_media_global_contracts(self):
        for name in ("openExternalMaterialLinkDrawer", "closeExternalMaterialLinkDrawer", "saveExternalMaterialLinkToExisting"):
            self.assertIn(f"window.{name}", self.source)
        for element_id in ("external-material-drawer", "external-material-id", "external-material-url", "external-material-preview"):
            self.assertIn(element_id, self.source)

    def test_external_media_api_and_admin_key_contract_stay_intact(self):
        self.assertIn("/api/materials/${encodeURIComponent(id)}/external-media", self.source)
        self.assertIn("method: 'PUT'", self.source)
        self.assertIn("'X-Admin-Key':key", self.source)
        self.assertIn("window.fetchAdminMaterials", self.source)
        self.assertIn("window.getAdminKey", self.source)

    def test_module_does_not_redefine_rbac_or_profile_metadata_as_policy(self):
        for forbidden in (
            "professional_title",
            "responsibility_tags",
            "professionalTitle",
            "responsibilityTags",
            "hasPermission",
            "canOpenWorkspace",
            "data-admin-role",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_asset_is_injected_and_checked_by_release_workflow(self):
        self.assertIn('/admin-external-media.js', ASSET_MANIFEST['system']['body'])
        self.assertIn("find static -type f -name '*.js'", self.workflow)
        self.assertIn("node --check", self.workflow)


if __name__ == "__main__":
    unittest.main()
