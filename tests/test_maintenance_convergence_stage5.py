import unittest
from pathlib import Path
from types import SimpleNamespace

import backup_restore
import sensitive_elevation_69


ROOT = Path(__file__).parents[1]


class MaintenanceConvergenceStage5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = ROOT.joinpath("backup_restore.py").read_text(encoding="utf-8")
        cls.canonical = ROOT.joinpath("teacher_app/maintenance/backup.py").read_text(encoding="utf-8")
        cls.routes = ROOT.joinpath("teacher_app/maintenance/backup_routes.py").read_text(encoding="utf-8")

    def test_backup_runtime_ownership_is_canonical(self):
        self.assertIn("def build_backup(", self.canonical)
        self.assertIn("def parse_backup_zip(", self.canonical)
        self.assertIn("def restore_backup(", self.canonical)
        self.assertIn("common_db.read_connection()", self.canonical)
        self.assertIn("common_db.transaction()", self.canonical)
        for marker in (
            "SELECT tablename FROM pg_tables",
            "SELECT name FROM sqlite_master",
            "INSERT OR IGNORE INTO",
            "ON CONFLICT DO NOTHING",
        ):
            self.assertNotIn(marker, self.adapter)

    def test_legacy_backup_module_is_thin_adapter(self):
        self.assertIn("teacher_app.maintenance", self.adapter)
        self.assertIn("sys.modules[__name__]", self.adapter)
        self.assertIn("maintenance_backup.build_backup", self.routes)
        self.assertIn("maintenance_backup.parse_backup_zip", self.routes)
        self.assertIn("maintenance_backup.restore_backup", self.routes)
        self.assertNotIn("hashlib", self.adapter)
        self.assertNotIn("zipfile", self.adapter)

    def test_mega_purge_requires_exact_teacher_root(self):
        calls = []
        good = SimpleNamespace(
            MEGA_ROOT_FOLDER="smh-teaching-materials",
            _mega_root_id=lambda: "/smh-teaching-materials",
            mega_destroy=lambda path: calls.append(path),
        )
        self.assertEqual(backup_restore._purge_teacher_mega_root(good), "smh-teaching-materials")
        self.assertEqual(calls, ["/smh-teaching-materials"])

        bad = SimpleNamespace(
            MEGA_ROOT_FOLDER="smh-teaching-materials",
            _mega_root_id=lambda: "/",
            mega_destroy=lambda _path: self.fail("account root must never be deleted"),
        )
        with self.assertRaises(RuntimeError):
            backup_restore._purge_teacher_mega_root(bad)

    def test_mega_purge_is_elevated_system_operation(self):
        required = sensitive_elevation_69._required_permissions(
            "POST", "/api/maintenance/storage/mega/purge-root"
        )
        self.assertEqual(required, ("system.manage",))
        self.assertIn('"PURGE-MEGA"', self.routes)


if __name__ == "__main__":
    unittest.main()
