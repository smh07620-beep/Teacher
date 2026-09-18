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
        ):
            self.assertIn(version, release_contract.REQUIRED_MIGRATIONS)

        registered = [version for version, _fn in schema_migrations.MIGRATIONS]
        for version in release_contract.REQUIRED_MIGRATIONS:
            self.assertIn(version, registered)

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
