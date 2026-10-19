from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CourseWizardRuntimeFix1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = ROOT.joinpath("static", "material-upload-client.js").read_text(encoding="utf-8")
        cls.wizard = ROOT.joinpath("static", "course-wizard-681.js").read_text(encoding="utf-8")
        cls.assets = ROOT.joinpath("teacher_app", "frontend", "assets.py").read_text(encoding="utf-8")
        cls.followup = ROOT.joinpath("teacher_app", "courses", "bundle_followup_routes.py").read_text(encoding="utf-8")
        cls.state = ROOT.joinpath("teacher_app", "courses", "bundle_followup.py").read_text(encoding="utf-8")

    def test_existing_direct_upload_job_is_reused_in_browser(self):
        for marker in (
            "queuedBody.alreadyQueued===true",
            "existingJobId",
            "accepted:true",
            "reused:true",
        ):
            self.assertIn(marker, self.client)

    def test_finish_action_avoids_double_course_hub_render(self):
        self.assertIn("return await openCourseWorkspaceNow()", self.wizard)
        self.assertIn("Course Wizard finish navigation failed", self.wizard)
        self.assertIn("window.AppWorkspaceRoutes.url('course-materials',{persona:'teacher'})", self.wizard)

    def test_legacy_runtime_fix_file_is_gone_and_duplicate_failure_panel_is_not_built(self):
        self.assertFalse(ROOT.joinpath("static", "course-wizard-runtime-fix-1014.js").exists())
        self.assertNotIn("course-wizard-runtime-fix-1014", self.assets)
        resilience = ROOT.joinpath("static", "teacher-ui-resilience-1014.js").read_text(encoding="utf-8")
        self.assertNotIn("worker-recent-failures-1014", resilience)

    def test_direct_upload_followup_claim_uses_file_identity_and_job_reuse(self):
        for marker in (
            "fingerprint=str(body.get(\"fingerprint\")",
            'kind_name="direct_upload_init"',
            '"alreadyQueued": True',
            "existingJobStatus",
            "bundleFollowupClaim",
            "followup_service.reset_claim",
            'app.view_functions["material_upload_init"] = retry_safe_direct_init',
        ):
            self.assertIn(marker, self.followup)
        for marker in (
            '"fingerprint": str(fingerprint or "").strip().lower()',
            '"fingerprintStrategy"',
            '"fingerprintPartSize"',
            "def reset_claim(",
        ):
            self.assertIn(marker, self.state)

    def test_retry_wait_detail_keeps_real_worker_exception(self):
        self.assertIn("本機 Worker 回報暫時失敗：{reason}", self.followup)
        self.assertIn('"error": reason', self.followup)
        self.assertIn('payload.get("retryAfterSeconds")', self.followup)


if __name__ == "__main__":
    unittest.main()
