import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class CourseBundleMigrationOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = ROOT.joinpath("teacher_app/maintenance/migrations.py").read_text(encoding="utf-8")
        cls.bundle = ROOT.joinpath("course_bundle_72.py").read_text(encoding="utf-8")
        cls.followup = ROOT.joinpath("course_bundle_followup_73.py").read_text(encoding="utf-8")
        cls.canonical_followup = ROOT.joinpath(
            "teacher_app", "courses", "bundle_followup.py"
        ).read_text(encoding="utf-8")

    def test_0072_and_0073_are_registered_only_in_schema_registry(self):
        self.assertIn('@migration("0072-course-bundle-idempotency")', self.schema)
        self.assertIn('@migration("0073-course-bundle-followups")', self.schema)
        self.assertIn("def _course_bundle_idempotency_72", self.schema)
        self.assertIn("def _course_bundle_followups_73", self.schema)

        for source in (self.bundle, self.followup):
            self.assertNotIn("MIGRATIONS", source)
            self.assertNotIn("migration(MIGRATION_ID)", source)

    def test_root_adapters_have_no_course_bundle_schema_ddl(self):
        for source in (self.bundle, self.followup):
            self.assertNotIn("CREATE TABLE IF NOT EXISTS course_bundle_", source)
            self.assertNotIn("CREATE INDEX IF NOT EXISTS idx_course_bundle_", source)

    def test_canonical_followup_owns_runtime_state_not_schema_registration(self):
        self.assertNotIn("def _course_bundle_followups_73", self.canonical_followup)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS course_bundle_followups", self.canonical_followup)
        self.assertIn("with common_db.transaction()", self.canonical_followup)


if __name__ == "__main__":
    unittest.main()
