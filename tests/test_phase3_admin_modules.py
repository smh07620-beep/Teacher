import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class Phase3AdminModuleSplitTests(unittest.TestCase):
    def test_results_module_is_loaded_as_phase3_override(self):
        frontend = ROOT.joinpath('pgy_frontend.py').read_text(encoding='utf-8')
        self.assertIn('/admin-results.js?v=7100', frontend)
        self.assertIn('/system-admin.js', ROOT.joinpath('static/system.html').read_text(encoding='utf-8'))

    def test_results_module_preserves_legacy_global_contracts(self):
        source = ROOT.joinpath('static/admin-results.js').read_text(encoding='utf-8')
        for name in ('openEssayReview', 'closeEssayReview', 'submitEssayReview'):
            self.assertIn(f'window.{name}', source)
        self.assertIn('/api/records/${encodeURIComponent(r.id)}/review', source)
        self.assertIn('X-Admin-Key', source)
        self.assertIn('renderAdminTable', source)

    def test_results_module_keeps_review_state_private(self):
        source = ROOT.joinpath('static/admin-results.js').read_text(encoding='utf-8')
        self.assertIn("'use strict'", source)
        self.assertIn('let currentReviewRecordIndex = null;', source)

    def test_course_material_module_is_loaded_after_results_override(self):
        frontend = ROOT.joinpath('pgy_frontend.py').read_text(encoding='utf-8')
        results_pos = frontend.index('/admin-results.js?v=7100')
        course_pos = frontend.index('/admin-course-material.js?v=7101')
        self.assertLess(results_pos, course_pos)

    def test_course_material_module_preserves_course_global_contracts(self):
        source = ROOT.joinpath('static/admin-course-material.js').read_text(encoding='utf-8')
        for name in (
            'adminCourseRowHTML',
            'paintAdminCourses',
            'optimisticInsertAdminCourse',
            'renderAdminCourses',
            'refreshAdminMaterialCourses',
            'adminDeleteCourse',
        ):
            self.assertIn(f'window.{name}', source)
        self.assertIn('/api/courses/admin?area=', source)
        self.assertIn("method:'DELETE'", source)
        self.assertIn('X-Admin-Key', source)
        self.assertIn('renderAdminCourseMaterialHub', source)

    def test_course_material_module_does_not_redefine_security_or_scope_policy(self):
        source = ROOT.joinpath('static/admin-course-material.js').read_text(encoding='utf-8')
        self.assertIn('getAdminKey', source)
        self.assertNotIn('professional_title', source)
        self.assertNotIn('responsibility_tags', source)
        self.assertNotIn('localStorage.setItem', source)
        self.assertNotIn('sessionStorage.setItem', source)


if __name__ == '__main__':
    unittest.main()
