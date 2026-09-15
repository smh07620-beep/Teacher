"""Static UI contracts for the 6.8.1 consolidated admin experience."""
import unittest
from pathlib import Path

ROOT=Path(__file__).parents[1]

class UxConsolidation681Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=ROOT.joinpath("static/system.html").read_text(encoding="utf-8")
        cls.js=ROOT.joinpath("static/system-admin.js").read_text(encoding="utf-8")

    def test_existing_wizard_is_course_first_and_multi_material(self):
        for marker in ("wizard-area", "wizard-group", "wizard-course-title", "wizard-material-files", "multiple", "建立整套課程"):
            self.assertIn(marker,self.html)
        self.assertIn("AI 候選題需人工確認",self.html)

    def test_assessment_navigation_is_unified(self):
        self.assertIn('admin-nav-assessment',self.html)
        self.assertIn('題庫與考卷',self.html)
        self.assertNotIn('admin-nav-questions',self.html)
        self.assertNotIn('admin-nav-exams',self.html)
        self.assertIn("if(name==='assessment'||name==='questions') return 'assessment'",self.js)

    def test_opening_admin_keeps_cached_sections_and_defers_worker_probe(self):
        toggle=self.js[self.js.index('async function toggleAdminModal'):self.js.index('async function renderAdminAnnouncements')]
        self.assertNotIn('Object.keys(adminSectionLoaded).forEach',toggle)
        workspace=self.js[self.js.index('async function switchAdminWorkspace'):self.js.index('function updateQuizWorkspacePresentation')]
        self.assertNotIn('renderMaterialJobs(false)',workspace)

    def test_external_material_drawer_uses_safe_backend_only(self):
        for marker in ('external-material-drawer','YouTube、Shorts','openExternalMaterialDrawer'):
            self.assertIn(marker,self.html)
        self.assertIn('/external-media',self.js)
        self.assertNotIn('iframe',self.html[self.html.index('external-material-drawer'):self.html.index('<!-- Footer -->')])
