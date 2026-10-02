import datetime as dt
import os
import unittest
from unittest.mock import patch

from teacher_app.worker import operations


NOW = dt.datetime(2026, 10, 2, 1, 0, tzinfo=dt.timezone.utc)


def heartbeat(worker_id: str, minutes_ago: int) -> dict:
    return {
        "worker_id": worker_id,
        "last_seen": (NOW - dt.timedelta(minutes=minutes_ago)).isoformat(),
        "capabilities": "{}",
        "current_job_id": "",
    }


class WorkerOfflineAlerts20261002Tests(unittest.TestCase):
    def test_default_ten_minute_threshold_ignores_short_gap_and_emits_prolonged_outage(self):
        env = {
            "MATERIAL_WORKER_ENABLED": "true",
            "MATERIAL_WORKER_OFFLINE_ALERT_SECONDS": "600",
            "MATERIAL_WORKER_HEARTBEAT_RETENTION_HOURS": "24",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(
            operations.repository,
            "list_heartbeats",
            return_value=[heartbeat("worker-9m", 9), heartbeat("worker-11m", 11)],
        ):
            result = operations.offline_worker_alerts(now=NOW)
        self.assertTrue(result["available"])
        self.assertEqual(result["thresholdSeconds"], 600)
        self.assertEqual([row["workerId"] for row in result["workers"]], ["worker-11m"])
        self.assertGreaterEqual(result["workers"][0]["offlineSeconds"], 660)

    def test_alert_threshold_is_bounded_to_five_through_sixty_minutes(self):
        with patch.object(operations.repository, "list_heartbeats", return_value=[]):
            with patch.dict(
                os.environ,
                {"MATERIAL_WORKER_ENABLED": "true", "MATERIAL_WORKER_OFFLINE_ALERT_SECONDS": "1"},
                clear=False,
            ):
                low = operations.offline_worker_alerts(now=NOW)
            with patch.dict(
                os.environ,
                {"MATERIAL_WORKER_ENABLED": "true", "MATERIAL_WORKER_OFFLINE_ALERT_SECONDS": "99999"},
                clear=False,
            ):
                high = operations.offline_worker_alerts(now=NOW)
        self.assertEqual(low["thresholdSeconds"], 300)
        self.assertEqual(high["thresholdSeconds"], 3600)

    def test_heartbeat_lookup_error_is_unavailable_not_offline(self):
        with patch.dict(
            os.environ,
            {"MATERIAL_WORKER_ENABLED": "true", "MATERIAL_WORKER_OFFLINE_ALERT_SECONDS": "600"},
            clear=False,
        ), patch.object(
            operations.repository,
            "list_heartbeats",
            side_effect=RuntimeError("database unavailable"),
        ):
            result = operations.offline_worker_alerts(now=NOW)
        self.assertFalse(result["available"])
        self.assertEqual(result["workers"], [])

    def test_disabled_worker_never_creates_offline_alert(self):
        with patch.dict(os.environ, {"MATERIAL_WORKER_ENABLED": "false"}, clear=False), patch.object(
            operations.repository, "list_heartbeats"
        ) as listing:
            result = operations.offline_worker_alerts(now=NOW)
        listing.assert_not_called()
        self.assertTrue(result["available"])
        self.assertEqual(result["workers"], [])


if __name__ == "__main__":
    unittest.main()
