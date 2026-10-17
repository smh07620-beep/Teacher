import gzip
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.frontend import assets

ROOT = Path(__file__).resolve().parents[1]


class StudentLeanAssetsTests(unittest.TestCase):
    def test_flag_is_off_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STUDENT_LEAN_ASSETS", None)
            self.assertFalse(assets.student_lean_enabled())
        with patch.dict(os.environ, {"STUDENT_LEAN_ASSETS": "1"}):
            self.assertTrue(assets.student_lean_enabled())

    def test_strip_removes_only_listed_scripts_with_or_without_version(self):
        html = ('<script defer src="/worker-status-70.js?v=7500"></script>\n'
                '<script defer src="/system-core.js?v=7500"></script>\n'
                '<script src="/system-admin.js"></script>')
        out = assets._strip_scripts(html, assets.STUDENT_LEAN_EXCLUDE)
        self.assertNotIn("worker-status-70", out)
        self.assertNotIn("system-admin.js", out)
        self.assertIn("/system-core.js", out)

    def test_every_excluded_file_exists_and_is_not_a_learner_script(self):
        for path in assets.STUDENT_LEAN_EXCLUDE:
            self.assertTrue((ROOT / "static" / path.lstrip("/")).exists(), path)
            self.assertFalse(path.startswith(("/learner", "/system-learner", "/teaching")), path)

    def test_savings_are_reported(self):
        total = sum(len(gzip.compress((ROOT / "static" / p.lstrip("/")).read_bytes())) for p in assets.STUDENT_LEAN_EXCLUDE)
        self.assertGreater(total, 20 * 1024)
