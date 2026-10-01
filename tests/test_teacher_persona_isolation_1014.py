from pathlib import Path
import unittest

from teacher_app.frontend.assets import ASSET_MANIFEST

ROOT = Path(__file__).resolve().parents[1]


class TeacherPersonaIsolation1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "teacher-persona-isolation-1014.js").read_text(encoding="utf-8")
        cls.system_focus = (ROOT / "static" / "system-admin-focus-1014.js").read_text(encoding="utf-8")
        cls.product_convergence = (ROOT / "static" / "product-convergence-101.js").read_text(encoding="utf-8")
        cls.body = ASSET_MANIFEST["system"]["body"]

    def test_teacher_persona_removes_platform_worker_navigation(self):
        for marker in (
            "persona === 'teacher'",
            "#admin-nav-worker,#admin-nav-people,#admin-nav-system,#admin-nav-maintenance,#admin-nav-audit",
            "教師工作區",
            "📚 教材與課程",
            "📝 評量與出題",
            "admin-section-worker",
        ):
            self.assertIn(marker, self.source)
        self.assertIn("teacherButtons.length !== 2", self.source)
        self.assertNotIn("['teacher-nav-media-1014'", self.source)
        self.assertNotIn("['teacher-nav-documents-1014'", self.source)

    def test_media_and_documents_move_to_contextual_tools(self):
        self.assertIn("🎙️ AI 媒體製作", self.product_convergence)
        self.assertIn("📄 紙本文件與匯出", self.product_convergence)
        self.assertIn("api.openMedia?.()", self.product_convergence)
        self.assertIn("api.openDocuments?.()", self.product_convergence)

    def test_legacy_persona_is_canonicalized_before_final_convergence_asset(self):
        self.assertIn("url.searchParams.set('persona', 'teacher')", self.source)
        self.assertIn("/product-convergence-101.js", self.body)
        self.assertEqual(self.body[-1], "/product-convergence-101.js")
        self.assertLess(self.body.index('/system-admin-focus-1014.js'), self.body.index('/teacher-persona-isolation-1014.js'))
        self.assertLess(self.body.index('/teacher-persona-isolation-1014.js'), self.body.index('/product-convergence-101.js'))

    def test_system_focus_only_runs_for_system_persona_or_legacy_system_workspace(self):
        self.assertIn("requestedPersona === 'system'", self.system_focus)
        self.assertIn("legacySystemWorkspaces.has(requestedWorkspace)", self.system_focus)
        self.assertNotIn("params.get('persona') !== 'teacher'", self.system_focus)


if __name__ == '__main__':
    unittest.main()
