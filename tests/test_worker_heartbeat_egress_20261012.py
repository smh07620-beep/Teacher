"""Regression tests for the Worker heartbeat database-egress fix (2026-10-12).

Background: every 2-second Worker claim used to read up to 50 heartbeat rows
(including the capabilities JSON) from Supabase just to find the caller's own
row, while one-shot ``github-fallback-<run_id>`` rows piled up forever.  These
tests pin the cheaper behaviour:

* the claim guard reads only the caller's own heartbeat row;
* stale heartbeat rows are pruned (fallback rows quickly, others after 24h);
* pruning is throttled and never touches the heartbeat that was just written.
"""
import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from teacher_app.worker import protocol_version
from teacher_app.worker import repository
from teacher_app.worker.protocol_version import (
    MATERIAL_WORKER_PROTOCOL_VERSION,
    MIN_MATERIAL_WORKER_PROTOCOL_VERSION,
)
from teacher_app.worker.schema import init_schema


NOW = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.timezone.utc)


def _stamp(hours_ago: float) -> str:
    return (NOW - dt.timedelta(hours=hours_ago)).isoformat()


class WorkerHeartbeatEgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "heartbeat-egress.sqlite"
        conn, kind = self.connect()
        try:
            init_schema(conn, kind)
            conn.execute(
                """
                CREATE TABLE material_worker_heartbeats (
                    worker_id TEXT PRIMARY KEY,
                    last_seen TEXT NOT NULL,
                    capabilities TEXT NOT NULL DEFAULT '{}',
                    current_job_id TEXT NOT NULL DEFAULT ''
                )
                """
            )
        finally:
            conn.close()
        protocol_version.install_web_guards()

    def connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def put(self, worker_id: str, hours_ago: float = 0, capabilities=None):
        repository._upsert_heartbeat_row(
            worker_id,
            last_seen=_stamp(hours_ago),
            capabilities=capabilities or {"protocolVersion": MATERIAL_WORKER_PROTOCOL_VERSION},
            connection_factory=self.connect,
        )

    def worker_ids(self) -> set[str]:
        return {
            item["worker_id"]
            for item in repository.list_heartbeats(200, connection_factory=self.connect)
        }

    # -- single-row read -------------------------------------------------
    def test_get_heartbeat_reads_only_the_requested_worker(self):
        self.put("worker-a", capabilities={"protocolVersion": 7, "marker": "a"})
        self.put("worker-b", capabilities={"protocolVersion": 7, "marker": "b"})
        item = repository.get_heartbeat("worker-a", connection_factory=self.connect)
        self.assertEqual(item["worker_id"], "worker-a")
        self.assertEqual(item["capabilities"]["marker"], "a")
        self.assertIsNone(repository.get_heartbeat("missing", connection_factory=self.connect))
        self.assertIsNone(repository.get_heartbeat("", connection_factory=self.connect))

    def test_claim_guard_does_not_scan_the_whole_heartbeat_table(self):
        self.put(
            "worker-old",
            capabilities={"protocolVersion": MIN_MATERIAL_WORKER_PROTOCOL_VERSION - 1},
        )
        with mock.patch.object(
            repository, "list_heartbeats", side_effect=AssertionError("full scan")
        ):
            claimed = repository.claim_next_material_job(
                "worker-old",
                now=NOW.isoformat(),
                connection_factory=self.connect,
            )
        # An old protocol is still refused (guard still works) ...
        self.assertIsNone(claimed)

    # -- pruning ---------------------------------------------------------
    def test_prune_removes_old_fallback_rows_quickly_and_keeps_fresh_ones(self):
        self.put("github-fallback-1", hours_ago=5)
        self.put("github-fallback-2", hours_ago=0.5)
        self.put("A8B5-TeacherWorker", hours_ago=0)
        removed = repository.prune_stale_heartbeats(now=NOW, connection_factory=self.connect)
        self.assertEqual(removed, 1)
        self.assertEqual(self.worker_ids(), {"github-fallback-2", "A8B5-TeacherWorker"})

    def test_prune_removes_other_workers_only_after_the_24h_window(self):
        self.put("laptop-worker", hours_ago=30)
        self.put("hospital-worker", hours_ago=10)
        repository.prune_stale_heartbeats(now=NOW, connection_factory=self.connect)
        self.assertEqual(self.worker_ids(), {"hospital-worker"})

    def test_prune_never_deletes_the_worker_that_just_reported(self):
        self.put("github-fallback-9", hours_ago=50)
        repository.prune_stale_heartbeats(
            keep_worker_id="github-fallback-9", now=NOW, connection_factory=self.connect
        )
        self.assertEqual(self.worker_ids(), {"github-fallback-9"})

    def test_prune_windows_are_configurable_from_the_environment(self):
        self.put("github-fallback-3", hours_ago=3)
        with mock.patch.dict(
            "os.environ", {"MATERIAL_WORKER_FALLBACK_HEARTBEAT_RETENTION_HOURS": "6"}
        ):
            repository.prune_stale_heartbeats(now=NOW, connection_factory=self.connect)
        self.assertEqual(self.worker_ids(), {"github-fallback-3"})

    # -- throttled housekeeping inside upsert_heartbeat ------------------
    def test_upsert_prunes_at_most_once_per_interval(self):
        self.put("github-fallback-old")
        self.backdate("github-fallback-old", hours_ago=9)

        # Interval has not elapsed yet -> no housekeeping, stale row remains.
        with mock.patch.object(repository, "_last_heartbeat_prune", repository.time.monotonic()):
            repository.upsert_heartbeat(
                "worker-a",
                last_seen=NOW.isoformat(),
                capabilities={},
                connection_factory=self.connect,
            )
        self.assertIn("github-fallback-old", self.worker_ids())

        # Interval elapsed -> housekeeping runs and removes the stale fallback row.
        with mock.patch.object(repository, "_last_heartbeat_prune", -1e9):
            repository.upsert_heartbeat(
                "worker-a",
                last_seen=NOW.isoformat(),
                capabilities={},
                connection_factory=self.connect,
            )
        self.assertNotIn("github-fallback-old", self.worker_ids())
        self.assertIn("worker-a", self.worker_ids())

    def test_housekeeping_failure_never_breaks_a_heartbeat(self):
        with mock.patch.object(repository, "_last_heartbeat_prune", -1e9), mock.patch.object(
            repository, "prune_stale_heartbeats", side_effect=RuntimeError("boom")
        ):
            repository.upsert_heartbeat(
                "worker-a",
                last_seen=NOW.isoformat(),
                capabilities={"protocolVersion": 1},
                connection_factory=self.connect,
            )
        self.assertIn("worker-a", self.worker_ids())

    # helper ---------------------------------------------------------------
    def backdate(self, worker_id: str, hours_ago: float) -> None:
        """Make one row look ``hours_ago`` hours old relative to the real clock."""
        conn, _ = self.connect()
        try:
            stamp = (
                dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago)
            ).isoformat()
            conn.execute(
                "UPDATE material_worker_heartbeats SET last_seen=? WHERE worker_id=?",
                (stamp, worker_id),
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
