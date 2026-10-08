"""MEGACMD_EXTRA_DIRS lets a SYSTEM-account Worker find MEGAcmd installed elsewhere."""
import os
import unittest
from unittest.mock import patch

from teacher_app.storage import worker_runtime


class ExtraDirsTests(unittest.TestCase):
    def _dirs(self, extra):
        env = {"MEGACMD_EXTRA_DIRS": extra, "LOCALAPPDATA": r"C:\Windows\System32\config\systemprofile\AppData\Local",
               "ProgramFiles": r"C:\Program Files", "ProgramFiles(x86)": r"C:\Program Files (x86)"}
        with patch.object(worker_runtime.sys, "platform", "win32"), patch.dict(os.environ, env, clear=False):
            return worker_runtime.WorkerMaterialStorageAdapter()._megacmd_windows_dirs()

    def test_extra_dirs_come_first_and_keep_defaults(self):
        dirs = self._dirs(r'C:\Users\a\AppData\Local\MEGAcmd; "D:\Tools\MEGAcmd" ;')
        self.assertEqual(dirs[0], r"C:\Users\a\AppData\Local\MEGAcmd")
        self.assertEqual(dirs[1], r"D:\Tools\MEGAcmd")
        self.assertIn(r"C:\Program Files\MEGAcmd", dirs)

    def test_blank_setting_changes_nothing(self):
        self.assertEqual(len(self._dirs("")), 3)


if __name__ == "__main__":
    unittest.main()
