from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SystemAdminRetirement74Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frontend = (ROOT / 'pgy_frontend.py').read_text(encoding='utf-8')
        cls.shared = (ROOT / 'static' / 'admin-runtime-shared.js').read_text(encoding='utf-8')
        cls.people = (ROOT / 'static' / 'admin-people-accounts.js').read_text(encoding='utf-8')
        cls.system = (ROOT / 'static' / 'admin-system-status.js').read_text(encoding='utf-8')
        cls.docx = (ROOT / 'static' / 'admin-results-docx-fallback.js').read_text(encoding='utf-8')
        cls.card = (ROOT / 'static' / 'admin-question-card.js').read_text(encoding='utf-8')
        cls.hub = (ROOT / 'static' / 'admin-course-material-hub.js').read_text(encoding='utf-8')

    def test_legacy_files_are_absent(self):
        self.assertFalse((ROOT / 'static' / 'system-admin.js').exists())
        self.assertFalse((ROOT / 'static' / 'question-authoring-ux-71.js').exists())

    def test_frontend_rewrites_historical_script_marker(self):
        self.assertIn('legacy_admin_marker', self.frontend)
        self.assertIn('runtime_admin_marker', self.frontend)
        self.assertIn('admin-runtime-shared.js?v=7400', self.frontend)
        self.assertIn('html.replace(legacy_admin_marker, runtime_admin_marker, 1)', self.frontend)
        self.assertNotIn("body_assets.append('<script defer src=\"/question-authoring-ux-71.js", self.frontend)

    def test_shared_runtime_contains_state_not_product_ui(self):
        for marker in ('getAdminKey', 'adminMaterialsCache', 'adminQuizCategoriesCache', 'adminCoursesCache', 'adminQuizQuestionCache', 'adminUserAccountsCache', 'adminRecords'):
            self.assertIn(marker, self.shared)
        for forbidden in ('insertAdjacentHTML', '/api/ai-questions/generate', '/api/material-jobs', 'renderAdminSystemStatus'):
            self.assertNotIn(forbidden, self.shared)

    def test_moved_owners_cover_former_unique_responsibilities(self):
        self.assertIn('window.renderAdminUserAccounts', self.people)
        self.assertIn('window.renderAdminPeople', self.people)
        self.assertIn('window.renderAdminSystemStatus', self.system)
        self.assertIn('window.exportRecordToWord', self.docx)
        self.assertIn('window.quizCategoryCardHTML', self.card)
        self.assertIn('window.renderAdminCourseMaterialHub', self.hub)


if __name__ == '__main__':
    unittest.main()
