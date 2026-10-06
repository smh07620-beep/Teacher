"""Static UI contracts for the 6.8.1 consolidated admin experience."""
import unittest
from pathlib import Path

ROOT=Path(__file__).parents[1]

class UxConsolidation681Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=ROOT.joinpath("static/system.html").read_text(encoding="utf-8")
        cls.workspace=ROOT.joinpath("static/admin-workspace.js").read_text(encoding="utf-8")
        cls.external=ROOT.joinpath("static/admin-external-media.js").read_text(encoding="utf-8")
        cls.external_client=ROOT.joinpath("static/external-material-681.js").read_text(encoding="utf-8")
        cls.learner=ROOT.joinpath("static/system-learner.js").read_text(encoding="utf-8")
        cls.learner_css=ROOT.joinpath("static/learner.css").read_text(encoding="utf-8")
        cls.portal_css=ROOT.joinpath("static/portal.css").read_text(encoding="utf-8")

    def test_existing_wizard_is_course_first_and_multi_material(self):
        for marker in (
            "wizard-area", "wizard-group", "wizard-course-title", "wizard-material-files",
            "wizard-exam-title", "multiple", "建立整套課程",
        ):
            self.assertIn(marker,self.html)
        self.assertIn("RC75_WORKSPACE_SIMPLIFIED",self.html)
        self.assertNotIn("AI 候選題需人工確認後才匯入",self.html)

    def test_assessment_navigation_is_unified(self):
        self.assertIn('admin-nav-assessment',self.html)
        self.assertIn('評量與出題',self.html)
        self.assertNotIn('admin-nav-questions',self.html)
        self.assertNotIn('admin-nav-exams',self.html)
        self.assertIn("name === 'assessment' || name === 'questions'",self.workspace)
        self.assertIn("return 'assessment'",self.workspace)

    def test_teacher_assessment_surface_includes_tracking_and_mobile_progress_is_direct(self):
        self.assertIn('評量與追蹤 Workspace', self.html)
        self.assertIn("switchLearningModule('progress')", self.html)
        mobile = self.html[self.html.index('v56-system-mobile-nav'):self.html.index('back-to-top')]
        self.assertIn("switchLearningModule('progress')", mobile)
        self.assertNotIn('<a href="/"><span>▥</span>進度</a>', mobile)

    def test_learner_resources_are_read_only_and_empty_states_are_explicit(self):
        self.assertNotIn('id="atlas-create-action"', self.html)
        self.assertIn('目前尚無 SOP 閱讀教材。', self.learner)
        self.assertIn('course-empty-row col-span-full', self.learner)
        self.assertIn('repeat(4,minmax(0,1fr))', self.portal_css)

    def test_learner_course_rows_are_compact_before_expansion(self):
        for marker in (
            '#course-overview .course-learning-summary{padding:.72rem .9rem',
            '#course-overview .teaching-meta{margin-top:.28rem',
            '#course-overview .course-learning-chevron{width:1.8rem',
        ):
            self.assertIn(marker, self.learner_css)

    def test_opening_admin_keeps_cached_sections_and_defers_worker_probe(self):
        self.assertIn("loaded: {content:false, quiz:false, word:false, pgy:false, results:false}",self.workspace)
        self.assertIn("if (!force && state.loaded[name]) return",self.workspace)
        self.assertIn('Storage/worker probes remain intentionally deferred until their panels open.',self.workspace)
        self.assertNotIn('renderMaterialJobs(false)',self.workspace)

    def test_external_material_drawer_uses_safe_backend_only(self):
        for marker in ('external-material-drawer','YouTube、Shorts、Vimeo','openExternalMaterialCreateDrawer'):
            self.assertIn(marker,self.html)
        self.assertIn('ExternalMediaClient',self.external)
        self.assertIn('/external-media',self.external_client)
        self.assertNotIn('<iframe',self.external.lower())
        drawer=self.html[self.html.index('external-material-drawer'):self.html.index('<!-- Footer -->')]
        self.assertNotIn('<iframe',drawer.lower())
