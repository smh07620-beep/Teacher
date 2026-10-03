from pathlib import Path
import unittest

from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class Teacher1014UiHotfixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = ASSET_MANIFEST["system"]["body"]
        cls.group_fix = (ROOT / "static" / "course-wizard-group-fix-1014.js").read_text(encoding="utf-8")
        cls.nav_fix = (ROOT / "static" / "teacher-workspace-nav-fix-1014.js").read_text(encoding="utf-8")
        cls.paper = (ROOT / "static" / "teacher-paper-template-manager-1014.js").read_text(encoding="utf-8")
        cls.media = (ROOT / "static" / "teacher-media-status-fix-1014.js").read_text(encoding="utf-8")

    def test_assets_are_injected_in_required_order(self):
        for asset in (
            "/teacher-workspace-nav-fix-1014.js",
            "/teacher-paper-template-manager-1014.js",
            "/teacher-media-status-fix-1014.js",
            "/teacher-media-free-tts-1014.js",
            "/teacher-persona-isolation-1014.js",
            "/course-wizard-group-fix-1014.js",
        ):
            self.assertIn(asset, self.body)
        self.assertLess(self.body.index('/teacher-workspace-1014.js'), self.body.index('/teacher-workspace-nav-fix-1014.js'))
        self.assertLess(self.body.index('/teacher-media-mvp-status-1014.js'), self.body.index('/teacher-media-status-fix-1014.js'))
        self.assertLess(self.body.index('/admin-question-bank.js'), self.body.index('/course-wizard-group-fix-1014.js'))
        self.assertLess(self.body.index('/system-admin-focus-1014.js'), self.body.index('/teacher-persona-isolation-1014.js'))

    def test_course_wizard_group_fix_uses_catalog_and_scope(self):
        for marker in ('rowsFor(area)', 'R.scopedTeacher', 'preferredGroup()', 'cw681-group', 'wizard-group'):
            self.assertIn(marker, self.group_fix)
        self.assertNotIn('X-Admin-Key', self.group_fix)

    def test_system_persona_stays_in_canonical_switcher_and_legacy_entry_targets_platform(self):
        self.assertNotIn("removeDuplicatePersona", self.nav_fix)
        self.assertIn("single owner of the persona switcher", self.nav_fix)
        self.assertIn('⚙ 平台管理', self.nav_fix)
        self.assertIn("workspace', 'people'", self.nav_fix)
        self.assertIn("persona', 'system'", self.nav_fix)

    def test_paper_workspace_can_import_official_docx_template(self):
        for marker in (
            '正式 SOP Word 範本',
            '匯入／更換 SOP Word 範本',
            '/api/doc-templates',
            "R.hasPermission('template.manage')",
            "method:'POST'",
            'accept=".docx',
        ):
            self.assertIn(marker, self.paper)
        self.assertNotIn('X-Admin-Key', self.paper)

    def test_ai_voice_readiness_checks_free_local_service_status(self):
        self.assertIn('/api/media-audio/status', self.media)
        self.assertIn('免費 AI 語音', self.media)
        self.assertIn('本機 Kokoro', self.media)
        self.assertNotIn('OPENAI_API_KEY', self.media)
        self.assertNotIn('X-Admin-Key', self.media)


if __name__ == '__main__':
    unittest.main()
