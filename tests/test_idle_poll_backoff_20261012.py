"""Idle Worker polling backs off (Render outbound bandwidth, 2026-10-12).

The two hospital Workers polled every 2 seconds all day, which on the Render
Hobby plan (5 GB/month included outbound) was the biggest steady consumer.
"""
import unittest
from pathlib import Path
from unittest import mock

from teacher_app.common.idle_backoff import (
    DEFAULT_IDLE_MAX_SECONDS,
    IDLE_MAX_CEILING_SECONDS,
    IdleBackoff,
    idle_max_seconds,
)

ROOT = Path(__file__).resolve().parents[1]


class IdleBackoffTests(unittest.TestCase):
    def test_starts_at_base_then_doubles_up_to_the_maximum(self):
        backoff = IdleBackoff(2, 15)
        delays = [backoff.idle_delay() for _ in range(25)]
        self.assertEqual(delays[:5], [2] * 5)
        self.assertEqual(delays[5:10], [4] * 5)
        self.assertEqual(delays[10:15], [8] * 5)
        self.assertEqual(delays[15:], [15] * 10)
        self.assertLessEqual(max(delays), 15)

    def test_work_resets_to_the_fast_interval(self):
        backoff = IdleBackoff(2, 15)
        for _ in range(30):
            backoff.idle_delay()
        self.assertEqual(backoff.idle_delay(), 15)
        backoff.reset()
        self.assertEqual(backoff.idle_delay(), 2)

    def test_maximum_equal_to_base_disables_the_slowdown(self):
        backoff = IdleBackoff(2, 2)
        self.assertEqual({backoff.idle_delay() for _ in range(40)}, {2})

    def test_idle_poll_cuts_requests_by_roughly_seven_times(self):
        backoff = IdleBackoff(2, 15)
        hour, polls = 0.0, 0
        while hour < 3600:
            hour += backoff.idle_delay()
            polls += 1
        self.assertLess(polls, 3600 / 2 / 6)

    def test_environment_value_is_clamped_below_the_online_window(self):
        name = "MATERIAL_WORKER_IDLE_POLL_MAX_SECONDS"
        with mock.patch.dict("os.environ", {}, clear=False):
            self.assertEqual(idle_max_seconds(name, 2), DEFAULT_IDLE_MAX_SECONDS)
        for raw, expected in (("30", 30), ("999", IDLE_MAX_CEILING_SECONDS), ("1", 2), ("abc", 15), ("", 15)):
            with mock.patch.dict("os.environ", {name: raw}):
                self.assertEqual(idle_max_seconds(name, 2), expected, raw)
        # Admin screens call a Worker online for 120 s after its last heartbeat.
        self.assertLess(IDLE_MAX_CEILING_SECONDS, 120)


class WorkerLoopWiringTests(unittest.TestCase):
    def test_both_workers_use_backoff_and_reset_on_work(self):
        material = (ROOT / "material_worker.py").read_text(encoding="utf-8")
        ai = (ROOT / "ai_question_worker.py").read_text(encoding="utf-8")
        for source in (material, ai):
            self.assertIn("IdleBackoff(", source)
            self.assertIn("idle_backoff.idle_delay()", source)
            self.assertIn("idle_backoff.reset()", source)
        self.assertIn("MATERIAL_WORKER_IDLE_POLL_MAX_SECONDS", material)
        self.assertIn("AI_QUESTION_WORKER_IDLE_POLL_MAX_SECONDS", ai)
        # The idle sleep must no longer be the fixed base interval.
        self.assertNotIn("time.sleep(poll_seconds)\n                except KeyboardInterrupt", ai)


if __name__ == "__main__":
    unittest.main()
