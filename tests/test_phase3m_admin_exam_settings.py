from pathlib import Path
import unittest

from pgy_frontend import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class Phase3MAdminExamSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "admin-exam-settings.js").read_text(encoding="utf-8")
        cls.ordered = dict(ASSET_MANIFEST["system"]["ordered"])["/system-admin.js"]

    def test_preserves_exam_settings_global_and_onclick_contracts(self):
        for name in ("adminEditQuizCategory", "openExamSettings", "saveExamSettings", "syncExamDrawModeUI", "updateExamQuotaTotal", "updateExamWorkflowUI", "previewCurrentExam", "reviewCurrentExam", "publishCurrentExam", "adminToggleBlindMode"):
            self.assertIn(f"window.{name}", self.source)

    def test_review_publish_and_settings_remain_server_authorized(self):
        for endpoint in ("/api/quiz-categories/${catId}", "/api/quiz-categories/${catId}/review", "/api/quiz-categories/${catId}/publish"):
            self.assertIn(endpoint, self.source)
        self.assertIn("'X-Admin-Key':key", self.source)
        self.assertIn("method:'POST'", self.source)
        self.assertIn("method:'PATCH'", self.source)

    def test_module_does_not_redefine_rbac_or_server_policy(self):
        for forbidden in ("professionalTitle", "responsibilityTags", "hasPermission", "data-admin-role"):
            self.assertNotIn(forbidden, self.source)

    def test_loads_after_legacy_and_before_wrappers(self):
        self.assertIn('/admin-exam-settings.js', self.ordered)


if __name__ == "__main__":
    unittest.main()
