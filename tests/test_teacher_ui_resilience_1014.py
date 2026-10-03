from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TeacherUiResilience1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT.joinpath("static", "teacher-ui-resilience-1014.js").read_text(encoding="utf-8")
        cls.css = ROOT.joinpath("static", "teacher-workspace-1014.css").read_text(encoding="utf-8")
        cls.assets = ROOT.joinpath("teacher_app", "frontend", "assets.py").read_text(encoding="utf-8")

    def test_progressive_help_is_opt_in_and_keeps_errors_visible(self):
        for marker in (
            "teacher-help-toggle-1014",
            "teacher-context-help-copy-1014",
            "teacher-help-visible-1014",
            "IMPORTANT_RE",
            "role=\"alert\"",
            "aria-live",
        ):
            self.assertIn(marker, self.source)
        self.assertIn(".teacher-context-help-copy-1014", self.css)
        self.assertIn("body.teacher-help-visible-1014", self.css)

    def test_assessment_scope_is_synced_before_refresh_and_empty_state_is_recoverable(self):
        for marker in (
            "syncAssessmentScope",
            "renderAdminQuizCategories",
            "assessment-empty-recovery-1014",
            "重新同步此範圍",
            "教材轉檔失敗不會刪除考卷資料",
        ):
            self.assertIn(marker, self.source)

    def test_worker_ui_exposes_fallback_and_failure_detail(self):
        for marker in (
            "worker-fallback-1014",
            "worker-recent-failures-1014",
            "LibreOffice",
            "FFmpeg",
            "job.error || job.detail",
            "/api/material-jobs?limit=30",
            "data.problemJobs || data.jobs || []",
        ):
            self.assertIn(marker, self.source)

    def test_system_layer_font_scale_is_not_tiny(self):
        self.assertIn("body.v56-system main .text-xs", self.css)
        self.assertIn("font-size: 0.875rem !important", self.css)
        self.assertIn('"/teacher-ui-resilience-1014.js"', self.assets)


if __name__ == "__main__":
    unittest.main()
