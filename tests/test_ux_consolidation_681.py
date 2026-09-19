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
        self.assertIn('題庫與考卷',self.html)
        self.assertNotIn('admin-nav-questions',self.html)
        self.assertNotIn('admin-nav-exams',self.html)
        self.assertIn("name === 'assessment' || name === 'questions'",self.workspace)
        self.assertIn("return 'assessment'",self.workspace)

    def test_opening_admin_keeps_cached_sections_and_defers_worker_probe(self):
        self.assertIn("loaded: {content:false, quiz:false, word:false, pgy:false, results:false}",self.workspace)
        self.assertIn("if (!force && state.loaded[name]) return",self.workspace)
        self.assertIn('Storage/worker probes remain intentionally deferred until their panels open.',self.workspace)
        self.assertNotIn('renderMaterialJobs(false)',self.workspace)

    def test_external_material_drawer_uses_safe_backend_only(self):
        for marker in ('external-material-drawer','YouTube、Vimeo','openExternalMaterialCreateDrawer'):
            self.assertIn(marker,self.html)
        self.assertIn('ExternalMediaClient',self.external)
        self.assertIn('/external-media',self.external_client)
        self.assertNotIn('<iframe',self.external.lower())
        drawer=self.html[self.html.index('external-material-drawer'):self.html.index('<!-- Footer -->')]
        self.assertNotIn('<iframe',drawer.lower())
