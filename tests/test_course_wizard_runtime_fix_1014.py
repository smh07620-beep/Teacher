from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CourseWizardRuntimeFix1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = ROOT.joinpath("static", "course-wizard-runtime-fix-1014.js").read_text(encoding="utf-8")
        cls.assets = ROOT.joinpath("teacher_app", "frontend", "assets.py").read_text(encoding="utf-8")
        cls.followup = ROOT.joinpath("teacher_app", "courses", "bundle_followup_routes.py").read_text(encoding="utf-8")
        cls.state = ROOT.joinpath("teacher_app", "courses", "bundle_followup.py").read_text(encoding="utf-8")

    def test_existing_direct_upload_job_is_reused_in_browser(self):
        for marker in (
            "body.alreadyQueued===true",
            "existingJobId",
            "accepted:true",
            "reused:true",
            "client.enqueue=guarded",
        ):
            self.assertIn(marker, self.guard)

    def test_finish_action_avoids_double_course_hub_render(self):
        self.assertIn("const canonical=window.courseWizard681OpenCourse", self.guard)
        self.assertIn("return await canonical()", self.guard)
        self.assertIn("Course Wizard finish navigation failed", self.guard)
        self.assertIn("window.location.assign('/system?module=course-materials')", self.guard)
        self.assertNotIn("renderAdminCourseMaterialHub", self.guard)

    def test_legacy_duplicate_worker_failure_panel_is_suppressed(self):
        for marker in (
            "worker-recent-failures-1014",
            "duplicate.hidden=true",
            "supersededBy='worker-status-70'",
        ):
            self.assertIn(marker, self.guard)

    def test_runtime_guard_is_injected_after_resilience_layer(self):
        self.assertIn('"/course-wizard-runtime-fix-1014.js"', self.assets)
        self.assertLess(
            self.assets.index('"/teacher-ui-resilience-1014.js"'),
            self.assets.index('"/course-wizard-runtime-fix-1014.js"'),
        )

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
