"""Static contracts for the canonical retry-safe Course Wizard flow."""
import unittest
from pathlib import Path

import release_contract

ROOT = Path(__file__).parents[1]


class CourseWizardIdempotentBundle72Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wizard = ROOT.joinpath("static", "course-wizard-681.js").read_text(encoding="utf-8")
        cls.adapter = ROOT.joinpath("course_bundle_72.py").read_text(encoding="utf-8")
        cls.bundle = ROOT.joinpath("teacher_app", "courses", "bundle.py").read_text(encoding="utf-8")
        cls.schema = ROOT.joinpath("schema_migrations.py").read_text(encoding="utf-8")
        cls.entry = ROOT.joinpath("pgy_app.py").read_text(encoding="utf-8")

    def test_wizard_uses_one_session_scoped_bundle_endpoint(self):
        self.assertIn("/api/course-bundles", self.wizard)
        self.assertIn("workflowId", self.wizard)
        self.assertIn("sessionStorage", self.wizard)
        self.assertIn("credentials:'same-origin'", self.wizard)
        self.assertNotIn("api('/api/courses'", self.wizard)
        self.assertNotIn("api('/api/quiz-categories'", self.wizard)
        self.assertNotIn("X-Admin-Key", self.wizard)
        self.assertNotIn("getAdminKey", self.wizard)

    def test_background_upload_remains_shared_followup_stage(self):
        self.assertIn("MaterialUploadClient.enqueue", self.wizard)
        self.assertIn("bundleWorkflowId", self.wizard)
        self.assertIn("pending-background", self.bundle)

    def test_bundle_route_uses_capability_rbac_and_canonical_transaction(self):
        self.assertIn('base.require_permission("course.manage")', self.adapter)
        self.assertIn('base.require_permission("question.manage")', self.adapter)
        self.assertIn("bundle_service.create_bundle", self.adapter)
        self.assertIn("with common_db.transaction()", self.bundle)
        self.assertNotIn("X-Admin-Key", self.adapter)
        self.assertNotIn("getAdminKey", self.adapter)
        self.assertIn("IDEMPOTENCY_KEY_REUSED", self.bundle)
        for runtime_sql in (
            "INSERT INTO courses",
            "INSERT INTO quiz_categories",
            "SELECT * FROM course_bundle_requests",
            "UPDATE course_bundle_requests SET",
        ):
            self.assertNotIn(runtime_sql, self.adapter)
            self.assertIn(runtime_sql, self.bundle)

    def test_migration_and_route_registration_order_remain_stable(self):
        self.assertIn("0072-course-bundle-idempotency", release_contract.REQUIRED_MIGRATIONS)
        self.assertIn('@migration("0072-course-bundle-idempotency")', self.schema)
        self.assertNotIn("migration(MIGRATION_ID)", self.adapter)
        self.assertLess(
            self.entry.index("app = register_schema_migrations"),
            self.entry.index("app = register_course_bundle_72"),
        )
        self.assertLess(
            self.entry.index("app = register_rbac_681"),
            self.entry.index("app = register_course_bundle_72"),
        )


if __name__ == "__main__":
    unittest.main()
