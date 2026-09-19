from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SystemWorkspaceSimplification75Tests(unittest.TestCase):
    def source(self, path):
        return ROOT.joinpath(path).read_text(encoding="utf-8")

    def test_persistent_step_tutorial_is_removed(self):
        html = self.source("static/system.html")
        self.assertIn("RC75_WORKSPACE_SIMPLIFIED", html)
        for marker in ("STEP 1", "STEP 2", "STEP 3", "STEP 4", "AI 候選題需人工確認後才匯入"):
            self.assertNotIn(marker, html)

    def test_course_creation_is_explicitly_routed_from_studio(self):
        studio = self.source("static/teacher-content-studio-71.js")
        ux = self.source("static/teacher-ux-convergence-72.js")
        self.assertIn("const canCourse", studio)
        self.assertIn("card('materials-manager'", studio)
        self.assertIn("mountMaterialManagerInStudio", studio)
        self.assertIn("mountCourseWizardInStudio", studio)
        self.assertIn("data-course-wizard-host-77", studio)
        self.assertIn("document.getElementById('course-wizard-681')", studio)
        self.assertNotIn("teacher75OpenCourseWizard", studio)
        self.assertIn("teacher75OpenCourseWizard", ux)
        self.assertIn("details.className='hidden", ux)

    def test_material_executor_is_not_a_daily_surface(self):
        studio = self.source("static/teacher-content-studio-71.js")
        self.assertIn("teacher75MaterialExecutorRoot", studio)
        self.assertNotIn("教材處理與背景工作", studio)
        self.assertNotIn("建立入口已統一", studio)

    def test_advanced_maintenance_is_system_admin_only_and_collapsed(self):
        shell = self.source("static/workspace-shell-70.js")
        self.assertIn("system-advanced-maintenance-75", shell)
        self.assertIn("if(!isSystemAdmin)return", shell)
        self.assertNotIn("admin-material-jobs-panel", shell)
        self.assertNotIn("data-system75-jobs", shell)
        self.assertIn("migrateMaterialsToMega", shell)
        self.assertIn("migrateLocalMaterialsToR2", shell)

    def test_session_rbac_copy_replaces_admin_key_guidance(self):
        html = self.source("static/system.html")
        self.assertNotIn("ADMIN_KEY、MEGA", html)
        self.assertIn("後台權限以登入 Session 與 RBAC 為準", html)


if __name__ == "__main__":
    unittest.main()
