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
        for name in ('adminCourseRowHTML','paintAdminCourses','optimisticInsertAdminCourse','renderAdminCourses','refreshAdminMaterialCourses','adminDeleteCourse'):
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

    def test_people_module_is_loaded_after_course_material_override(self):
        frontend = ROOT.joinpath('pgy_frontend.py').read_text(encoding='utf-8')
        course_pos = frontend.index('/admin-course-material.js?v=7101')
        people_pos = frontend.index('/admin-people.js?v=7113')
        self.assertLess(course_pos, people_pos)

    def test_people_module_preserves_profile_editor_contracts(self):
        source = ROOT.joinpath('static/admin-people.js').read_text(encoding='utf-8')
        for name in ('adminProfileTags','adminUserRoleSummary','ensureAdminUserEditor','adminSyncProfileTagChecks','adminSetProfileTag','openAdminUserEditor','closeAdminUserEditor','saveAdminUserEditor'):
            self.assertIn(f'window.{name}', source)
        self.assertIn('/api/users/${encodeURIComponent(username)}', source)
        self.assertIn('/training-audience', source)
        self.assertIn("method:'PATCH'", source)
        self.assertIn('professionalTitle', source)
        self.assertIn('responsibilityTags', source)
        self.assertIn('pgyLearner', source)

    def test_people_profile_metadata_never_becomes_rbac_input(self):
        source = ROOT.joinpath('static/admin-people.js').read_text(encoding='utf-8')
        self.assertIn('不參與 RBAC 判斷', source)
        self.assertIn('不會授予教師簽核、組長複核或管理權限', source)
        self.assertNotIn('professionalTitle===', source)
        self.assertNotIn('responsibilityTags.includes', source)
        self.assertNotIn('pgyLearner===', source)
        self.assertNotIn('localStorage.setItem', source)
        self.assertNotIn('sessionStorage.setItem', source)

    def test_announcements_module_is_loaded_after_people_override(self):
        frontend = ROOT.joinpath('pgy_frontend.py').read_text(encoding='utf-8')
        people_pos = frontend.index('/admin-people.js?v=7113')
        announcements_pos = frontend.index('/admin-announcements.js?v=7103')
        self.assertLess(people_pos, announcements_pos)

    def test_announcements_module_preserves_admin_global_contracts(self):
        source = ROOT.joinpath('static/admin-announcements.js').read_text(encoding='utf-8')
        for name in ('renderAdminAnnouncements','createAdminAnnouncement','toggleAdminAnnouncement','deleteAdminAnnouncement'):
            self.assertIn(f'window.{name}', source)
        self.assertIn('/api/announcements/admin', source)
        self.assertIn("method:'POST'", source)
        self.assertIn("method:'PATCH'", source)
        self.assertIn("method:'DELETE'", source)
        self.assertIn('X-Admin-Key', source)

    def test_system_module_is_loaded_after_announcements_override(self):
        frontend = ROOT.joinpath('pgy_frontend.py').read_text(encoding='utf-8')
        announcements_pos = frontend.index('/admin-announcements.js?v=7103')
        system_pos = frontend.index('/admin-system.js?v=7104')
        self.assertLess(announcements_pos, system_pos)

    def test_system_module_preserves_storage_global_contracts(self):
        source = ROOT.joinpath('static/admin-system.js').read_text(encoding='utf-8')
        for name in ('renderStorageStatus','migrateMaterialsToMega','migrateMaterialsToGoogleDrive','migrateLocalMaterialsToR2'):
            self.assertIn(f'window.{name}', source)
        self.assertIn('/api/storage-status', source)
        self.assertIn('/api/storage/migrate-to-mega', source)
        self.assertIn('/api/storage/migrate-to-gdrive', source)
        self.assertIn('/api/storage/migrate-to-r2', source)
        self.assertIn('X-Admin-Key', source)

    def test_system_module_keeps_existing_security_boundary(self):
        source = ROOT.joinpath('static/admin-system.js').read_text(encoding='utf-8')
        self.assertIn('getAdminKey', source)
        self.assertNotIn('professional_title', source)
        self.assertNotIn('responsibility_tags', source)
        self.assertNotIn('localStorage.setItem', source)
        self.assertNotIn('sessionStorage.setItem', source)


if __name__ == '__main__':
    unittest.main()
