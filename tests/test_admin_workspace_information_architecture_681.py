import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AdminWorkspaceInformationArchitecture681Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath("static", "system.html").read_text(encoding="utf-8")
        cls.css = ROOT.joinpath("static", "admin.css").read_text(encoding="utf-8")
        cls.course = ROOT.joinpath("static", "admin-course-material.js").read_text(encoding="utf-8")
        cls.wizard = ROOT.joinpath("static", "course-wizard-681.js").read_text(encoding="utf-8")
        cls.results = ROOT.joinpath("static", "admin-results-workspace.js").read_text(encoding="utf-8")
        cls.system = ROOT.joinpath("static", "admin-system.js").read_text(encoding="utf-8")
        cls.questions = ROOT.joinpath("static", "admin-question-bank.js").read_text(encoding="utf-8")
        cls.people = ROOT.joinpath("static", "admin-people.js").read_text(encoding="utf-8")
        cls.csp = ROOT.joinpath("static", "system-csp-actions.js").read_text(encoding="utf-8")

    def test_course_workspace_is_browse_first_with_compact_scope_toolbar(self):
        for marker in (
            'id="admin-course-scope"',
            'COURSES & MATERIALS WORKSPACE',
            '教材與課程 Workspace',
            'id="course-workspace-create-course"',
            'id="course-workspace-add-material"',
            'id="course-wizard-legacy-fields"',
        ):
            self.assertIn(marker, self.html)
        self.assertIn('#admin-course-workspace > #course-wizard-681', self.css)
        self.assertIn('display: none !important', self.css)
        self.assertIn("const old=el('course-wizard-legacy-fields')", self.wizard)

    def test_course_hub_has_dashboard_counts_before_expandable_course_details(self):
        for marker in (
            'admin-course-dashboard',
            'admin-course-summary-grid',
            '課程',
            '教材',
            '考卷',
            '待整理',
            'admin-course-list',
        ):
            self.assertIn(marker, self.course)

    def test_teacher_review_gets_a_dedicated_work_summary(self):
        for marker in (
            'id="teacher-review-overview"',
            'id="teacher-review-pending-count"',
            'id="teacher-review-people-count"',
            'id="teacher-review-essay-count"',
        ):
            self.assertIn(marker, self.html)
        self.assertIn('function renderTeacherReviewOverview(records)', self.results)
        self.assertIn("overview?.classList.toggle('hidden', !scoring)", self.results)
        self.assertIn('window.renderTeacherReviewOverview = renderTeacherReviewOverview', self.results)

    def test_assessment_workspace_is_list_first_with_scope_and_status_summary(self):
        for marker in (
            'ASSESSMENT & AUTHORING WORKSPACE',
            '評量與出題 Workspace',
            'id="assessment-workspace-create-exam"',
            'id="admin-quiz-scope-78"',
            'id="admin-quiz-total-count"',
            'id="admin-quiz-published-count"',
            'id="admin-quiz-approved-count"',
            'id="admin-quiz-draft-count"',
        ):
            self.assertIn(marker, self.html)
        self.assertIn('function renderQuizOverview78(', self.questions)
        self.assertIn('window.renderQuizOverview78=renderQuizOverview78', self.questions)
        self.assertIn('.admin-quiz-summary-grid', self.css)

    def test_people_workspace_is_directory_first_and_creation_is_secondary(self):
        for marker in (
            'PEOPLE & ACCESS',
            'id="admin-people-account-summary"',
            'id="admin-user-search"',
            'id="admin-user-role-filter"',
            'id="admin-user-state-filter"',
            'id="admin-user-create-panel"',
        ):
            self.assertIn(marker, self.html)
        self.assertIn('function filteredAdminUserAccounts()', self.people)
        self.assertIn('function updateAdminUserSummary()', self.people)
        self.assertIn('window.filterAdminUserAccounts=paintAdminUserAccounts', self.people)
        self.assertIn("'filterAdminUserAccounts'", self.csp)
        self.assertIn('.admin-people-filterbar', self.css)

    def test_word_and_results_have_dedicated_page_headers(self):
        self.assertIn('WORD TEMPLATES', self.html)
        self.assertIn('id="results-workspace-overview"', self.html)
        self.assertIn('RESULTS & ANALYTICS', self.html)
        self.assertIn("resultsOverview?.classList.toggle('hidden', scoring)", self.results)
        self.assertIn('.admin-results-overview', self.css)

    def test_system_workspace_separates_health_storage_security_and_communication(self):
        for marker in (
            'admin-system-overview',
            'admin-system-health-grid',
            'admin-system-detail-grid',
            'admin-system-storage-card',
            'admin-system-safety-card',
            'admin-announcement-workspace',
        ):
            self.assertIn(marker, self.html)
        self.assertIn('admin-system-status-card', self.system)
        self.assertIn('is-good', self.system)
        self.assertIn('is-warning', self.system)
        self.assertIn('is-error', self.system)

    def test_workspace_content_reflows_on_tablet_and_phone(self):
        self.assertIn('@media (max-width: 980px)', self.css)
        self.assertIn('@media (max-width: 620px)', self.css)
        self.assertIn('.admin-course-summary-grid', self.css)
        self.assertIn('.admin-quiz-summary-grid', self.css)
        self.assertIn('.admin-people-summary-grid', self.css)
        self.assertIn('.admin-teacher-review-stats', self.css)
        self.assertIn('.admin-system-health-grid', self.css)


if __name__ == "__main__":
    unittest.main()
