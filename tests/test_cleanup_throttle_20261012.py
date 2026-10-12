"""Regression tests for the claim-time housekeeping throttle (2026-10-12).

The material Worker claims work every ~2 seconds and each claim used to run
``runtime.cleanup_budget_state()``, which re-read every finished material job
(payload included) from the database.  That repeated read was a major source of
Supabase egress, so housekeeping is now limited to once per interval.
"""
import unittest
from unittest import mock

from teacher_app.common import throttle
from teacher_app.materials import job_runtime
from teacher_app.worker import web_runtime


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class ThrottledTests(unittest.TestCase):
    def test_first_call_runs_then_calls_inside_the_interval_are_skipped(self):
        clock = _Clock()
        calls = []
        wrapped = throttle.throttled(lambda: calls.append(1), interval_seconds=300, clock=clock)
        wrapped()
        clock.now += 2
        wrapped()
        clock.now += 120
        wrapped()
        self.assertEqual(len(calls), 1)
        clock.now += 200  # 322s after the first run
        wrapped()
        self.assertEqual(len(calls), 2)

    def test_zero_interval_disables_the_throttle(self):
        clock = _Clock()
        calls = []
        wrapped = throttle.throttled(lambda: calls.append(1), interval_seconds=0, clock=clock)
        for _ in range(4):
            wrapped()
        self.assertEqual(len(calls), 4)

    def test_failed_housekeeping_is_not_retried_on_every_claim(self):
        clock = _Clock()
        attempts = []

        def boom():
            attempts.append(1)
            raise RuntimeError("storage offline")

        wrapped = throttle.throttled(boom, interval_seconds=300, clock=clock)
        with self.assertRaises(RuntimeError):
            wrapped()
        clock.now += 2
        wrapped()  # skipped silently, not retried
        self.assertEqual(len(attempts), 1)

    def test_interval_comes_from_the_environment_with_safe_fallbacks(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            self.assertEqual(throttle.cleanup_interval_seconds(), 300.0)
        for raw, expected in (("60", 60.0), ("0", 0.0), ("-5", 0.0), ("99999", 3600.0), ("abc", 300.0), ("", 300.0)):
            with mock.patch.dict("os.environ", {"MATERIAL_CLEANUP_INTERVAL_SECONDS": raw}):
                self.assertEqual(throttle.cleanup_interval_seconds(), expected, raw)


class CanonicalRuntimeThrottleTests(unittest.TestCase):
    def _call_five_times(self, runtime, patched):
        for _ in range(5):
            runtime.cleanup_budget_state()
        return patched.call_count

    def test_worker_web_runtime_cleans_once_for_many_claims(self):
        with mock.patch.object(web_runtime, "MaterialStagingRuntime"), mock.patch.object(
            web_runtime.r2_budget, "cleanup_budget_state"
        ) as cleanup, mock.patch.dict("os.environ", {"MATERIAL_CLEANUP_INTERVAL_SECONDS": "300"}):
            runtime = web_runtime.build_canonical_runtime(paths_provider=lambda: None)
            self.assertEqual(self._call_five_times(runtime, cleanup), 1)

    def test_material_job_runtime_cleans_once_for_many_refreshes(self):
        with mock.patch.object(job_runtime, "MaterialStagingRuntime"), mock.patch.object(
            job_runtime.r2_budget, "cleanup_budget_state"
        ) as cleanup, mock.patch.dict("os.environ", {"MATERIAL_CLEANUP_INTERVAL_SECONDS": "300"}):
            runtime = job_runtime.build_canonical_runtime(paths_provider=lambda: None)
            self.assertEqual(self._call_five_times(runtime, cleanup), 1)

    def test_throttle_can_be_switched_off_for_debugging(self):
        with mock.patch.object(web_runtime, "MaterialStagingRuntime"), mock.patch.object(
            web_runtime.r2_budget, "cleanup_budget_state"
        ) as cleanup, mock.patch.dict("os.environ", {"MATERIAL_CLEANUP_INTERVAL_SECONDS": "0"}):
            runtime = web_runtime.build_canonical_runtime(paths_provider=lambda: None)
            self.assertEqual(self._call_five_times(runtime, cleanup), 5)


if __name__ == "__main__":
    unittest.main()
