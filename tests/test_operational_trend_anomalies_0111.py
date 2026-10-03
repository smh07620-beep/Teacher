import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.common import db as common_db
from teacher_app.maintenance.operational_incident_migration import operational_incidents_108
from teacher_app.maintenance.operational_incident_response_migration import operational_incident_response_109
from teacher_app.maintenance.operational_metrics_migration import operational_metrics_history_110
from teacher_app.notifications import incidents
from teacher_app.operations import history
from teacher_app.worker import schema as worker_schema


NOW = dt.datetime(2026, 10, 4, 8, 0, tzinfo=dt.timezone.utc)


class OperationalTrendAnomalies0111Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "trend.sqlite"

        def connect():
            conn = sqlite3.connect(str(self.path), timeout=30)
            conn.row_factory = sqlite3.Row
            conn.isolation_level = None
            return conn, "sqlite"

        self.connect = connect
        conn, kind = connect()
        try:
            worker_schema.init_schema(conn, kind)
            operational_incidents_108(conn, kind)
            operational_incident_response_109(conn, kind)
            operational_metrics_history_110(conn, kind)
        finally:
            conn.close()
        patcher = patch.object(common_db, "get_connection", side_effect=self.connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def insert_snapshot(
        self,
        when,
        *,
        pending=0,
        oldest=0,
        active=1,
        known=1,
        available=True,
    ):
        conn, _kind = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO operational_metric_snapshots(
                    id,sampled_at,pending_jobs,processing_jobs,retry_jobs,failed_jobs,
                    oldest_pending_age_seconds,recent_terminal_jobs,recent_failure_rate,
                    average_completed_duration_seconds,healthy_processing_jobs,
                    heartbeat_delayed_jobs,stalled_jobs,active_workers,known_workers,
                    worker_status_available,open_incidents,critical_incidents
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "ops:" + when.isoformat(),
                    when.isoformat(),
                    pending,
                    0,
                    0,
                    0,
                    oldest,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    active,
                    known,
                    1 if available else 0,
                    0,
                    0,
                ),
            )
        finally:
            conn.close()

    def insert_completed_job(self, job_id, finished, duration_seconds):
        started = finished - dt.timedelta(seconds=duration_seconds)
        conn, _kind = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO material_jobs(
                    id,status,priority,created_at,updated_at,available_at,
                    started_at,finished_at,staging_path
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    job_id,
                    "completed",
                    50,
                    started.isoformat(),
                    finished.isoformat(),
                    started.isoformat(),
                    started.isoformat(),
                    finished.isoformat(),
                    f"/tmp/{job_id}",
                ),
            )
        finally:
            conn.close()

    def insert_incident_event(self, key, code, when):
        conn, _kind = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO operational_incident_events(
                    event_key,incident_key,incident_type,category,severity,error_code,
                    resource_id,generation,event_type,occurred_at,opened_at,resolved_at,
                    duration_seconds
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    key,
                    "source:" + key,
                    "error_burst",
                    "storage",
                    "warning",
                    code,
                    code,
                    1,
                    "opened",
                    when.isoformat(),
                    when.isoformat(),
                    "",
                    0,
                ),
            )
        finally:
            conn.close()

    def test_single_queue_spike_does_not_become_trend_incident(self):
        values = [0, 0, 7, 0, 0, 0]
        for index, pending in enumerate(values):
            self.insert_snapshot(
                NOW - dt.timedelta(minutes=(5 - index) * 10),
                pending=pending,
                oldest=900 if pending else 0,
            )
        analysis = history.analyze_operational_trends(now=NOW)
        codes = {row["code"] for row in analysis["signals"]}
        self.assertNotIn("TREND_QUEUE_GROWTH", codes)
        self.assertNotIn("WORKER_CAPACITY_PRESSURE", codes)

    def test_sustained_queue_growth_with_one_worker_flags_capacity_pressure(self):
        pending_values = [1, 2, 3, 4, 5, 6]
        oldest_values = [100, 200, 300, 600, 700, 800]
        for index, (pending, oldest) in enumerate(zip(pending_values, oldest_values)):
            self.insert_snapshot(
                NOW - dt.timedelta(minutes=(5 - index) * 10),
                pending=pending,
                oldest=oldest,
                active=1,
                known=1,
            )
        analysis = history.analyze_operational_trends(now=NOW)
        codes = {row["code"] for row in analysis["signals"]}
        self.assertIn("TREND_QUEUE_GROWTH", codes)
        self.assertIn("WORKER_CAPACITY_PRESSURE", codes)
        self.assertEqual(analysis["capacity"]["state"], "pressure")
        candidates = history.trend_incident_candidates(now=NOW)
        keys = {row["incidentKey"] for row in candidates}
        self.assertIn("trend:trend_queue_growth", keys)
        self.assertIn("trend:worker_capacity_pressure", keys)

    def test_processing_slowdown_requires_two_real_completed_job_windows(self):
        for index in range(3):
            self.insert_completed_job(
                f"prev-{index}",
                NOW - dt.timedelta(hours=7, minutes=index),
                60,
            )
            self.insert_completed_job(
                f"current-{index}",
                NOW - dt.timedelta(hours=1, minutes=index),
                180,
            )
        analysis = history.analyze_operational_trends(now=NOW)
        slowdown = next(
            row for row in analysis["signals"]
            if row["code"] == "TREND_PROCESSING_SLOWDOWN"
        )
        self.assertEqual(slowdown["evidence"]["currentJobs"], 3)
        self.assertEqual(slowdown["evidence"]["previousJobs"], 3)
        self.assertGreater(
            slowdown["evidence"]["currentP95Seconds"],
            slowdown["evidence"]["previousP95Seconds"],
        )

    def test_incident_frequency_compares_equal_windows_and_ignores_trend_self_events(self):
        self.insert_incident_event(
            "previous-r2",
            "R2_STORAGE",
            NOW - dt.timedelta(hours=30),
        )
        for index in range(3):
            self.insert_incident_event(
                f"current-r2-{index}",
                "R2_STORAGE",
                NOW - dt.timedelta(hours=index + 1),
            )
        for index in range(5):
            self.insert_incident_event(
                f"trend-self-{index}",
                "TREND_QUEUE_GROWTH",
                NOW - dt.timedelta(hours=index + 1),
            )

        analysis = history.analyze_operational_trends(now=NOW)
        frequency = [
            row for row in analysis["signals"]
            if row["code"] == "TREND_INCIDENT_FREQUENCY"
        ]
        self.assertEqual(len(frequency), 1)
        self.assertEqual(frequency[0]["componentCode"], "R2_STORAGE")
        self.assertEqual(frequency[0]["evidence"]["currentCount"], 3)
        self.assertEqual(frequency[0]["evidence"]["previousCount"], 1)

    def test_trend_candidate_uses_existing_incident_lifecycle_and_auto_resolves(self):
        trend_candidate = {
            "incidentKey": "trend:trend_queue_growth",
            "incidentType": "trend_anomaly",
            "category": "trend",
            "severity": "warning",
            "title": "教材 Queue 持續上升",
            "detail": "queue rising",
            "action": "inspect capacity",
            "errorCode": "TREND_QUEUE_GROWTH",
            "resourceId": "TREND_QUEUE_GROWTH",
        }
        with patch.object(
            incidents.worker_operations,
            "operational_incident_candidates",
            return_value=[],
        ), patch.object(
            incidents,
            "_ai_job_incident_candidates",
            return_value=[],
        ), patch.object(
            incidents.operational_history,
            "trend_incident_candidates",
            return_value=[trend_candidate],
        ), patch.object(
            incidents.worker_operations,
            "online_worker_recovery_keys",
            return_value=set(),
        ):
            opened = incidents.sync_operational_incidents(now=NOW)
        self.assertEqual(len(opened["opened"]), 1)
        self.assertEqual(opened["opened"][0]["errorCode"], "TREND_QUEUE_GROWTH")
        self.assertTrue(opened["opened"][0]["runbook"]["steps"])

        with patch.object(
            incidents.worker_operations,
            "operational_incident_candidates",
            return_value=[],
        ), patch.object(
            incidents,
            "_ai_job_incident_candidates",
            return_value=[],
        ), patch.object(
            incidents.operational_history,
            "trend_incident_candidates",
            return_value=[],
        ), patch.object(
            incidents.worker_operations,
            "online_worker_recovery_keys",
            return_value=set(),
        ):
            resolved = incidents.sync_operational_incidents(
                now=NOW + dt.timedelta(minutes=10)
            )
        self.assertEqual(len(resolved["resolved"]), 1)
        self.assertEqual(resolved["resolved"][0]["incidentType"], "trend_anomaly")


if __name__ == "__main__":
    unittest.main()
