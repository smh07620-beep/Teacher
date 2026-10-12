"""A Worker's stderr output must not make the Windows supervisor quit (2026-10-12)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SupervisorStderrTests(unittest.TestCase):
    def _launch_block(self, name, launch):
        text = (ROOT / name).read_text(encoding="utf-8")
        start = text.index(launch)
        return text[text.rfind("$previousErrorPreference = $ErrorActionPreference", 0, start): start + 900]

    def test_material_supervisor_keeps_going_when_the_worker_writes_to_stderr(self):
        block = self._launch_block("run_material_worker_autostart.ps1", "& $python -u -m teacher_app.worker.material_worker_entry")
        self.assertIn('$ErrorActionPreference = "Continue"', block)
        self.assertIn("finally", block)
        self.assertNotIn("exit 32", block)
        self.assertIn("$workerExit = 32", block)

    def test_ai_supervisor_keeps_going_when_the_worker_writes_to_stderr(self):
        block = self._launch_block("run_ai_worker_autostart.ps1", "& $python -u $entry")
        self.assertIn('$ErrorActionPreference = "Continue"', block)
        self.assertNotIn("exit 32", block)
        self.assertIn("$workerExit = 32", block)

    def test_launch_failure_is_counted_as_a_retryable_crash(self):
        text = (ROOT / "run_material_worker_autostart.ps1").read_text(encoding="utf-8")
        self.assertRegex(text, re.compile(r"\$workerExit = 32.*?\$crashRestarts\+\+", re.S))


if __name__ == "__main__":
    unittest.main()
