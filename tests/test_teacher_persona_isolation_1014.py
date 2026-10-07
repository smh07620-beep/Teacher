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
        cls.teacher_workspace = (ROOT / "static" / "teacher-workspace-1014.js").read_text(encoding="utf-8")
        cls.nav_fix = (ROOT / "static" / "teacher-workspace-nav-fix-1014.js").read_text(encoding="utf-8")
        cls.admin_router = (ROOT / "static" / "admin-workspace.js").read_text(encoding="utf-8")
        cls.body = ASSET_MANIFEST["system"]["body"]

    def test_teacher_persona_removes_platform_worker_navigation(self):
        for marker in (
            "persona === 'teacher'",
            "#admin-nav-worker,#admin-nav-people,#admin-nav-system,#admin-nav-maintenance,#admin-nav-audit",
            "教師工作區",
            "📚 教材與課程",
            "📝 評量與追蹤",
            "admin-section-worker",
        ):
            self.assertIn(marker, self.source)
        self.assertIn("teacherButtons.length !== 2", self.source)
        self.assertNotIn("['teacher-nav-media-1014'", self.source)
        self.assertNotIn("['teacher-nav-documents-1014'", self.source)

    def test_media_documents_and_help_do_not_duplicate_primary_navigation(self):
        self.assertIn("document.getElementById('teacher-context-tools-101')?.remove()", self.product_convergence)
        self.assertIn("teacher-inline-support-1014", self.teacher_workspace)
        self.assertIn("teacher-guide-open-1014", self.teacher_workspace)
        self.assertNotIn("teacher-account-open-1014", self.teacher_workspace)
        self.assertNotIn("utilityButton('teacher-announcements-open-1014'", self.teacher_workspace)
        self.assertNotIn("utilityButton('teacher-documents-open-1014'", self.teacher_workspace)
        self.assertIn("openMedia", self.teacher_workspace)
        self.assertIn("openDocuments", self.teacher_workspace)

    def test_review_results_and_tracking_keep_assessment_primary_nav_active(self):
        self.assertIn("['assessment','teacher','results','compliance','pgy'].includes(workspace)", self.source)
        self.assertIn("mode === 'documents' || mode === 'announcements'", self.source)

    def test_legacy_persona_is_canonicalized_before_product_and_p1_layers(self):
        self.assertIn("url.searchParams.set('persona', 'teacher')", self.source)
        for asset in ("/product-convergence-101.js", "/teacher-action-queue-1024.js"):
            self.assertIn(asset, self.body)
        self.assertLess(self.body.index('/system-admin-focus-1014.js'), self.body.index('/teacher-persona-isolation-1014.js'))
        self.assertLess(self.body.index('/teacher-persona-isolation-1014.js'), self.body.index('/product-convergence-101.js'))
        self.assertLess(self.body.index('/product-convergence-101.js'), self.body.index('/teacher-action-queue-1024.js'))

    def test_platform_workspaces_never_mount_teacher_persona_hooks(self):
        self.assertIn("teacherOwnedWorkspaces.has(requestedWorkspace)", self.teacher_workspace)
        self.assertNotIn("requestedPersona !== 'system'", self.teacher_workspace)
        self.assertIn("SYSTEM_WORKSPACES.has(workspace)", self.admin_router)
        self.assertIn("url.searchParams.set('persona', 'system')", self.admin_router)
        self.assertIn("window.location.assign(workspaceUrl(requested || workspace))", self.admin_router)

    def test_system_persona_button_is_not_removed_after_first_paint(self):
        self.assertNotIn("removeDuplicatePersona", self.nav_fix)
        self.assertIn("single owner of the persona switcher", self.nav_fix)

    def test_system_focus_only_runs_for_system_persona_or_legacy_system_workspace(self):
        self.assertIn("requestedPersona === 'system'", self.system_focus)
        self.assertIn("legacySystemWorkspaces.has(requestedWorkspace)", self.system_focus)
        self.assertNotIn("params.get('persona') !== 'teacher'", self.system_focus)


if __name__ == '__main__':
    unittest.main()
