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


class AssessmentGroupSelectKeepsUserChoiceTests(unittest.TestCase):
    """Choosing another group must not be reset to the default group on re-render."""

    def test_sync_keeps_the_group_the_user_picked(self):
        import json
        import shutil
        import subprocess

        node = shutil.which("node")
        if not node:
            self.skipTest("node is not available")
        source = ROOT.joinpath("static", "teacher-ui-resilience-1014.js").read_text(encoding="utf-8")
        start = source.index("  function assessmentScope() {")
        end = source.index("  const canonicalQuizRender")
        script = """
const options = values => values.map(value => ({ value }));
const area = { value: 'internal', options: options(['internal', 'pgy']) };
const group = { value: 'grpMicro', options: options(['grpBio', 'grpMicro', 'grpSero']) };
const elements = { 'admin-quiz-area': area, 'admin-quiz-group': group };
const document = { getElementById: id => elements[id] || null };
const window = { location: { search: '' }, currentTrainingArea: 'internal', currentGroupKey: 'grpBio' };
%s
const first = syncAssessmentScope();
group.value = '';
const second = syncAssessmentScope();
console.log(JSON.stringify({ first, second, finalGroup: group.value }));
""" % source[start:end]
        result = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        self.assertEqual(data["first"]["group"], "grpMicro")
        # 選單尚未有值（例如剛重建）時才退回預設組別
        self.assertEqual(data["second"]["group"], "grpBio")
