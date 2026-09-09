import unittest
from pathlib import Path

import health_65
import schema_migrations


ROOT = Path(__file__).parents[1]


class Release66Tests(unittest.TestCase):
    def test_release_version_entrypoint_and_migration_contract(self):
        self.assertEqual(
            ROOT.joinpath("VERSION").read_text(encoding="utf-8").strip(),
            "6.6.0",
        )
        self.assertIn(
            "pgy_app:app",
            ROOT.joinpath("run_web.sh").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "0066-additive-rbac-pgy-signing",
            health_65.REQUIRED_MIGRATIONS,
        )
        self.assertIn(
            "0066-additive-rbac-pgy-signing",
            [version for version, _fn in schema_migrations.MIGRATIONS],
        )

    def test_release_document_records_security_and_operational_invariants(self):
        document = ROOT.joinpath("ARCHITECTURE_6_6.md").read_text(encoding="utf-8")
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
