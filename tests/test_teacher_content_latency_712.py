import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class TeacherContentLatency712Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.latency = ROOT.joinpath('static/teacher-content-latency-712.js').read_text(encoding='utf-8')
        cls.frontend = ROOT.joinpath('pgy_frontend.py').read_text(encoding='utf-8')
        cls.assessments = ROOT.joinpath('teacher_app/assessments/service.py').read_text(encoding='utf-8')
        cls.backend_perf = ROOT.joinpath('assessment_performance_712.py').read_text(encoding='utf-8')
        cls.entrypoint = ROOT.joinpath('pgy_app.py').read_text(encoding='utf-8')

    def test_latency_guard_is_injected_after_dedicated_panels(self):
        self.assertIn('/teacher-content-latency-712.js?v=7120', self.frontend)
        self.assertLess(
            self.frontend.index('/teacher-content-tool-panels-710.js?v=7110'),
            self.frontend.index('/teacher-content-latency-712.js?v=7120'),
        )

    def test_exam_lists_use_abort_and_dedup_cache(self):
        for marker in ('AbortController', 'FETCH_TIMEOUT_MS=15000', 'sessionStorage', 'inflight', 'warmCurrentScope'):
            self.assertIn(marker, self.latency)
        self.assertIn("ADMIN_PATH='/api/quiz-categories/admin'", self.latency)
        self.assertIn('CATEGORY_PATHS.has(meta.url.pathname)', self.latency)
        self.assertIn('const controller=new AbortController()', self.latency)
        self.assertIn("window.renderAdminQuizCategories(false)", self.latency)
        self.assertNotIn("window.renderAdminQuizCategories(true)", self.latency)

    def test_exam_actions_do_not_use_legacy_force_refresh_path(self):
        for marker in ('openManualQuestion', 'openSettings', 'showSkeleton', 'waitForPanel'):
            self.assertIn(marker, self.latency)
        self.assertIn("action==='question'||action==='image'||action==='video'", self.latency)
        self.assertIn("action==='settings'", self.latency)

    def test_assessment_list_cache_bridges_public_and_admin_reads(self):
        self.assertIn('_CATEGORY_LIST_CACHE_TTL_SECONDS = 15.0', self.assessments)
        self.assertIn('include_inactive=True', self.assessments)
        self.assertIn('return [item for item in full_list if bool(item.get("active"))]', self.assessments)
        self.assertIn('_clear_category_list_cache', self.assessments)

    def test_backend_avoids_duplicate_auth_lookup_and_adds_query_indexes(self):
        self.assertIn('@migration("0074-assessment-list-indexes")', self.backend_perf)
        self.assertIn('idx_quiz_categories_scope_list', self.backend_perf)
        self.assertIn('idx_quiz_questions_category_active', self.backend_perf)
        self.assertIn('has_request_context()', self.backend_perf)
        self.assertIn('_teacher712_current_user', self.backend_perf)
        self.assertIn('register_assessment_performance_712', self.entrypoint)

    def test_browser_javascript_syntax(self):
        completed = subprocess.run(
            ['node', '--check', str(ROOT / 'static' / 'teacher-content-latency-712.js')],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)


if __name__ == '__main__':
    unittest.main()
