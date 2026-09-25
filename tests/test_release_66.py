import unittest
from pathlib import Path

import health_65
import release_contract
import schema_migrations


ROOT = Path(__file__).parents[1]


class ReleaseContractTests(unittest.TestCase):
    def test_release_version_entrypoint_and_migration_contract(self):
        self.assertEqual(
            release_contract.version_file_value(),
            release_contract.RELEASE_VERSION,
        )
        self.assertEqual(
            health_65.app_version(),
            release_contract.RELEASE_VERSION,
        )
        self.assertRegex(release_contract.RELEASE_VERSION, r"^\d+\.\d+\.\d+$")
        self.assertIn(
            release_contract.ENTRYPOINT,
            ROOT.joinpath("run_web.sh").read_text(encoding="utf-8"),
        )

        self.assertEqual(
            tuple(health_65.REQUIRED_MIGRATIONS),
            release_contract.REQUIRED_MIGRATIONS,
        )
        self.assertEqual(
            release_contract.REQUIRED_RELEASE_MIGRATION,
            release_contract.REQUIRED_MIGRATIONS[-1],
        )
        for version in (
            "0066-additive-rbac-pgy-signing",
            "0067-r2-free-budget-guard",
            "0070-material-search-and-atlas",
            "0071-pgy-learner-audience",
            "0072-course-bundle-idempotency",
            "0073-course-bundle-followups",
            "0074-assessment-list-indexes",
            "0075-ai-question-jobs",
            "0076-assessment-reviewer-identity",
            "0077-general-audit-events",
            "0078-item-analytics-metrics",
            "0079-provider-publish-receipts",
            "0080-external-media-verification",
            "0081-question-version-history",
            "0082-version-aware-item-analytics",
            "0083-learning-assignments",
            "0084-material-version-retraining",
            "0086-notification-read-state",
        ):
            self.assertIn(version, release_contract.REQUIRED_MIGRATIONS)

        registered = [version for version, _fn in schema_migrations.MIGRATIONS]
        self.assertEqual(tuple(registered), release_contract.REQUIRED_MIGRATIONS)
        for version in release_contract.REQUIRED_MIGRATIONS:
            self.assertIn(version, registered)

    def test_formal_release_and_internal_generation_are_deliberately_distinct(self):
        self.assertEqual(release_contract.RELEASE_VERSION, "6.8.1")
        self.assertEqual(release_contract.INTERNAL_GENERATION, "7.9 / RC79")
        readme = ROOT.joinpath("README.md").read_text(encoding="utf-8")
        architecture = ROOT.joinpath("ARCHITECTURE.md").read_text(encoding="utf-8")
        for document in (readme, architecture):
            self.assertIn("6.8.1", document)
            self.assertIn("7.9 / RC79", document)
        self.assertIn("Formal release SemVer remains `6.8.1`", ROOT.joinpath("RUNTIME_OWNERSHIP_MAP_STAGE5.md").read_text(encoding="utf-8"))

    def test_release_document_records_security_and_operational_invariants(self):
        document = ROOT.joinpath("docs", "archive", "ARCHITECTURE_HISTORY.md").read_text(encoding="utf-8")
        for marker in (
            "multi-role",
            "primary legacy role",
            "Dual signing",
            "exam identifier",
            "Sequential",
            "review source",
            "system settings",
            "0066-additive-rbac-pgy-signing",
            "server is authoritative",
            "two different accounts",
            "pgy_app:app",
            "Teacher-6.6.0-release",
        ):
            self.assertIn(marker, document)


if __name__ == "__main__":
    unittest.main()
