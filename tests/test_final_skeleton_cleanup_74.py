from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FinalSkeletonCleanup74Tests(unittest.TestCase):
    def source(self, path):
        return ROOT.joinpath(path).read_text(encoding="utf-8")

    def test_public_portals_have_no_dead_v575_management_markup(self):
        for path in ("static/index.html", "static/area-internal.html", "static/area-pgy.html"):
            html = self.source(path)
            self.assertNotIn('class="v575-manage-direct"', html)
            self.assertIn('/portal-v56.js?v=7400', html)
        self.assertIn('data-pgy-management-only', self.source('static/area-pgy.html'))
        self.assertIn('class="v575-manage-direct"', self.source('static/system.html'))

    def test_public_navigation_no_longer_carries_dead_management_compat(self):
        portal = self.source('static/portal-v56.js')
        nav = self.source('static/portal-navigation-73.js')
        self.assertNotIn("$$('.v575-manage-direct')", portal)
        self.assertNotIn("document.querySelectorAll('.v575-manage-direct').forEach(entry=>entry.remove())", nav)

    def test_teaching_css_is_retired_and_learner_css_owns_classes(self):
        self.assertFalse(ROOT.joinpath('static/teaching.css').exists())
        learner = self.source('static/learner.css')
        self.assertIn('.teaching-welcome', learner)
        self.assertIn('.teaching-plan', learner)

    def test_obsolete_backend_routes_are_physically_retired(self):
        app = self.source('app.py')
        smart = self.source('smart_learning_67.py')
        for route in ('/api/groups', '/api/training-areas', '/api/admin/background-jobs/status'):
            self.assertNotIn(route, app)
        for route in ('/api/docx-atlas-preview/', '/api/learning-analytics', '/api/media-processing/capability'):
            self.assertNotIn(route, smart)
        self.assertIn('def preview_docx_atlas(', smart)
        self.assertIn('/api/atlas/import-docx/', self.source('atlas_70.py'))
        self.assertIn('/api/training-command-center/learning-analytics', self.source('teacher_app/command_center/routes.py'))
        self.assertIn('/api/material-jobs', app)

    def test_completed_backend_features_have_canonical_frontend_consumers(self):
        actions = self.source('static/admin-question-actions.js')
        workspace = self.source('static/workspace-shell-70.js')
        self.assertIn('/api/quiz-questions/batch-delete', actions)
        self.assertIn('/api/security/status', workspace)
        self.assertIn('security-status-70', workspace)

    def test_review_links_wrap_canonical_question_payload_owner(self):
        review = self.source('static/review-links-66.js')
        frontend = self.source('pgy_frontend.py')
        self.assertIn('window.adminBuildQuestionPayload', review)
        self.assertNotIn('adminPayloadFromQuestionEditor', review)
        self.assertGreater(frontend.index('/review-links-66.js?v=7400'), frontend.index('/admin-question-actions.js?v=7120'))

    def test_legacy_admin_ownership_moved_to_canonical_modules(self):
        legacy = self.source('static/system-admin.js')
        owners = {
            'static/admin-course-material.js': 'renderAdminCourseMaterialHub',
            'static/admin-question-bank.js': 'quizCategoryCardHTML',
            'static/admin-people.js': 'renderAdminUserAccounts',
            'static/admin-system.js': 'renderAdminSystemStatus',
            'static/admin-exam-settings.js': 'difficultyLabel',
            'static/learner-result-chart.js': 'renderCategoryChart',
            'static/learner-exam-controls.js': 'resetCurrentQuiz',
        }
        for path, symbol in owners.items():
            self.assertIn(symbol, self.source(path))
            self.assertNotIn(f'function {symbol}(', legacy)
        self.assertIn('async function getAdminKey()', legacy)
        self.assertIn('let cachedTemplateBuffer = null', legacy)
        self.assertIn('let pendingExportRecordIndex = null', legacy)


if __name__ == '__main__':
    unittest.main()
