"""Regressions for Worker heartbeat retention and status presentation."""
from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.worker import operations


ROOT = Path(__file__).parents[1]


class WorkerHeartbeatRetentionTests(unittest.TestCase):
    def test_status_keeps_online_and_recent_offline_but_hides_old_history(self):
        now = dt.datetime.now(dt.timezone.utc)
        heartbeats = [
            {
                "worker_id": "worker-online",
                "last_seen": (now - dt.timedelta(seconds=30)).isoformat(),
                "capabilities": {"ffmpeg": {"available": True}},
                "current_job_id": "",
            },
            {
                "worker_id": "worker-recent-offline",
                "last_seen": (now - dt.timedelta(minutes=10)).isoformat(),
                "capabilities": {"libreOffice": {"available": True}},
                "current_job_id": "",
            },
            {
                "worker_id": "worker-old",
                "last_seen": (now - dt.timedelta(hours=25)).isoformat(),
                "capabilities": {},
                "current_job_id": "",
            },
        ]
        with (
            patch.object(operations.repository, "queue_aggregates", return_value={}),
            patch.object(operations.repository, "list_material_jobs", return_value=[]),
            patch.object(operations.repository, "list_heartbeats", return_value=heartbeats),
            patch.object(operations.r2_budget, "status", return_value={}),
            patch.dict("os.environ", {"MATERIAL_WORKER_HEARTBEAT_RETENTION_HOURS": "24"}, clear=False),
        ):
            result = operations.status(lambda: {"available": True, "shared": True})

        workers = {item["workerId"]: item for item in result["workers"]}
        self.assertEqual(set(workers), {"worker-online", "worker-recent-offline"})
        self.assertEqual(workers["worker-online"]["status"], "online")
        self.assertEqual(workers["worker-recent-offline"]["status"], "offline")

    def test_worker_ui_prioritizes_active_and_collapses_recent_offline(self):
        source = ROOT.joinpath("static", "worker-status-70.js").read_text(encoding="utf-8")
        for marker in (
            "const activeWorkers = workers.filter",
            "const recentOfflineWorkers = workers.filter",
            "近期離線 Worker",
            "最近 24 小時內的離線紀錄",
            "activeWorkers.map(workerCard)",
            "recentOfflineWorkers.map(workerCard)",
        ):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
