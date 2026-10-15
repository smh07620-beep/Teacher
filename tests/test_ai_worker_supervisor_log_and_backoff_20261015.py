"""AI Worker supervisor: persistent log, longer retries, stable-run reset (2026-10-15)."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AIWorkerSupervisorLogAndBackoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "run_ai_worker_autostart.ps1").read_text(encoding="utf-8")

    def test_transcript_log_is_written_under_a_gitignored_logs_folder(self):
        self.assertIn("Start-Transcript", self.text)
        self.assertIn('Join-Path $root "logs"', self.text)
        ignored = {line.strip() for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
        self.assertIn("logs/", ignored)

    def test_logging_failure_cannot_stop_the_worker(self):
        block = self.text[self.text.index("function Start-TeacherAIWorkerLog"):self.text.index("function Write-TeacherAIWorkerLog")]
        self.assertIn("catch", block)
        self.assertNotIn("throw", block)

    def test_retries_are_longer_with_growing_delays(self):
        self.assertIn("$maxCrashRestarts = 10", self.text)
        self.assertIn("$restartDelays = @(5, 15, 30, 60, 120, 180, 300, 300, 300, 300)", self.text)
        self.assertIn("Start-Sleep -Seconds $delay", self.text)

    def test_stable_run_resets_the_crash_counter_before_counting(self):
        reset = self.text.index("$runTimer.Elapsed.TotalSeconds -ge $stableRunSeconds")
        count = self.text.index("$crashRestarts++")
        self.assertLess(reset, count)

    def test_approved_restart_and_limit_event_are_preserved(self):
        self.assertIn("$workerExit -eq 75", self.text)
        self.assertIn("-EventId 3105", self.text)
        self.assertNotIn("git fetch", self.text)


if __name__ == "__main__":
    unittest.main()
