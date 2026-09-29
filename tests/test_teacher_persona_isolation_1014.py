from pathlib import Path
import unittest

from teacher_app.frontend.assets import ASSET_MANIFEST

ROOT = Path(__file__).resolve().parents[1]


class TeacherPersonaIsolation1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "teacher-persona-isolation-1014.js").read_text(encoding="utf-8")
        cls.system_focus = (ROOT / "static" / "system-admin-focus-1014.js").read_text(encoding="utf-8")
        cls.body = ASSET_MANIFEST["system"]["body"]

    def test_teacher_persona_removes_platform_worker_navigation(self):
        for marker in (
            "persona === 'teacher'",
            "#admin-nav-worker,#admin-nav-people,#admin-nav-system,#admin-nav-maintenance,#admin-nav-audit",
            "教師工作台",
            "📚 教材與課程",
            "🎙️ 媒體製作",
            "📝 評量與出題",
            "📄 紙本文件與匯出",
            "admin-section-worker",
        ):
            self.assertIn(marker, self.source)

    def test_legacy_persona_is_canonicalized_and_final_asset_runs_last(self):
        self.assertIn("url.searchParams.set('persona', 'teacher')", self.source)
        self.assertEqual(self.body[-1], "/teacher-persona-isolation-1014.js")
        self.assertLess(self.body.index('/system-admin-focus-1014.js'), self.body.index('/teacher-persona-isolation-1014.js'))

    def test_system_focus_only_runs_for_system_persona_or_legacy_system_workspace(self):
        self.assertIn("requestedPersona === 'system'", self.system_focus)
        self.assertIn("legacySystemWorkspaces.has(requestedWorkspace)", self.system_focus)
        self.assertNotIn("params.get('persona') !== 'teacher'", self.system_focus)


if __name__ == '__main__':
    unittest.main()
