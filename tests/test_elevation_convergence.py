from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class ElevationConvergenceTests(unittest.TestCase):
    def test_elevation_state_sql_is_canonical(self):
        adapter = ROOT.joinpath("admin_elevation_68.py").read_text(encoding="utf-8")
        canonical = ROOT.joinpath("teacher_app/auth/elevation.py").read_text(encoding="utf-8")

        self.assertIn("from teacher_app.auth.elevation import", adapter)
        self.assertIn("register_admin_elevation_compat as register_admin_elevation", adapter)
        for sql_marker in (
            "SELECT elevated_at,expires_at,session_version",
            "INSERT INTO admin_elevations",
        ):
            self.assertNotIn(sql_marker, adapter)
            self.assertIn(sql_marker, canonical)

    def test_sensitive_path_policy_is_canonical(self):
        adapter = ROOT.joinpath("sensitive_elevation_69.py").read_text(encoding="utf-8")
        policy = ROOT.joinpath("teacher_app/auth/elevation_policy.py").read_text(encoding="utf-8")
        canonical = ROOT.joinpath("teacher_app/auth/elevation.py").read_text(encoding="utf-8")

        self.assertIn("from teacher_app.auth.elevation import", adapter)
        self.assertIn("def register_sensitive_elevation(", canonical)
        self.assertNotIn("from flask", adapter)
        self.assertNotIn('"/api/storage/migrate-to-"', adapter)
        self.assertNotIn('"/api/maintenance/restore"', adapter)
        self.assertIn('"/api/storage/migrate-to-"', policy)
        self.assertIn('"/api/maintenance/restore"', policy)


if __name__ == "__main__":
    unittest.main()
