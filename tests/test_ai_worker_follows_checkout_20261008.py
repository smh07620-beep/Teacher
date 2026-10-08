"""The AI Worker restarts itself (exit 75) once its checkout was updated, but never touches git itself."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import ai_question_worker

ROOT = Path(__file__).resolve().parents[1]


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class CheckoutWatcherTests(unittest.TestCase):
    def _watcher(self, shas, clock, **env):
        values = list(shas)

        def identity():
            return {"workerSha": values[0] if len(values) == 1 else values.pop(0)}

        with patch.dict(os.environ, env, clear=False):
            return ai_question_worker._CheckoutWatcher(interval_seconds=60, identity=identity, clock=clock)

    def test_no_restart_while_the_checkout_is_unchanged(self):
        clock = _Clock()
        watcher = self._watcher(["aaaaaaa"], clock)
        clock.now += 120
        self.assertFalse(watcher.changed())

    def test_restart_requested_after_head_moves(self):
        clock = _Clock()
        watcher = self._watcher(["aaaaaaa", "bbbbbbb"], clock)
        clock.now += 120
        self.assertTrue(watcher.changed())

    def test_check_is_rate_limited(self):
        clock = _Clock()
        watcher = self._watcher(["aaaaaaa", "bbbbbbb"], clock)
        clock.now += 10  # earlier than the 60 second interval
        self.assertFalse(watcher.changed())

    def test_missing_git_never_triggers_a_restart(self):
        clock = _Clock()
        watcher = self._watcher(["", "bbbbbbb"], clock)
        clock.now += 120
        self.assertFalse(watcher.changed())
        clock = _Clock()
        watcher = self._watcher(["aaaaaaa", ""], clock)
        clock.now += 120
        self.assertFalse(watcher.changed())

    def test_can_be_switched_off(self):
        clock = _Clock()
        watcher = self._watcher(["aaaaaaa", "bbbbbbb"], clock, AI_WORKER_RESTART_ON_UPDATE="false")
        clock.now += 120
        self.assertFalse(watcher.changed())


class WorkerLoopContractTests(unittest.TestCase):
    def test_restart_only_happens_when_idle_and_uses_supervisor_exit_code(self):
        source = ROOT.joinpath("ai_question_worker.py").read_text(encoding="utf-8")
        idle = source.index("if did_work:\n                        continue")
        restart = source.index("checkout_watcher.changed()")
        sleep = source.index("time.sleep(poll_seconds)\n                except KeyboardInterrupt")
        self.assertLess(idle, restart)
        self.assertLess(restart, sleep)
        self.assertIn("return 75", source[restart:sleep])

    def test_ai_launcher_still_has_no_git_or_updater(self):
        launcher = ROOT.joinpath("run_ai_worker_autostart.ps1").read_text(encoding="utf-8")
        for forbidden in ("update_material_worker.ps1", "git fetch", "git pull", "git reset"):
            self.assertNotIn(forbidden, launcher)


if __name__ == "__main__":
    unittest.main()
