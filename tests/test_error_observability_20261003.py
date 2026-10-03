import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ErrorObservability20261003Tests(unittest.TestCase):
    def test_external_io_fallbacks_emit_safe_operational_logs(self):
        r2 = ROOT.joinpath("teacher_app", "storage", "r2_budget.py").read_text(encoding="utf-8")
        reminders = ROOT.joinpath("teacher_app", "notifications", "reminders.py").read_text(encoding="utf-8")
        pgy = ROOT.joinpath("teacher_app", "pgy", "assessment_routes.py").read_text(encoding="utf-8")
        materials = ROOT.joinpath("teacher_app", "materials", "service.py").read_text(encoding="utf-8")
        scope_filter = ROOT.joinpath("teacher_app", "common", "scope_filter.py").read_text(encoding="utf-8")

        for marker, source in (
            ("R2 upload session status count failed", r2),
            ("R2 stale upload session lookup failed", r2),
            ("R2 stale upload remote cleanup failed", r2),
            ("R2 stale upload state transition failed", r2),
            ("email notification claim release failed", reminders),
            ("email reminder event projection failed", reminders),
            ("worker offline reminder send failed", reminders),
            ("PGY template temp cleanup failed", pgy),
            ("PGY EPA reference import failed", pgy),
            ("PGY template delete failed", pgy),
            ("material category label lookup failed", materials),
            ("scope resource lookup failed", scope_filter),
            ("scope authorization resolution denied", scope_filter),
        ):
            self.assertIn(marker, source)

        for source in (r2, reminders, pgy, materials, scope_filter):
            self.assertIn("error_type=%s", source)


if __name__ == "__main__":
    unittest.main()
