import datetime as dt
import os
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


NOW = dt.datetime(2026, 10, 4, 10, 0, tzinfo=dt.timezone.utc)
FORECAST_ENV = {
    "OPERATIONS_FORECAST_WINDOW_HOURS": "2",
    "OPERATIONS_FORECAST_MIN_COMPLETED_JOBS": "3",
    "OPERATIONS_FORECAST_MIN_SNAPSHOT_COVERAGE": "0.5",
}


class CapacityForecast0112Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "capacity.sqlite"

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

    def insert_job(
        self,
        job_id,
        *,
        created,
        status="queued",
        duration_seconds=None,
    ):
        started = ""
        finished = ""
        updated = created
        if duration_seconds is not None:
            started_dt = created + dt.timedelta(minutes=1)
            finished_dt = started_dt + dt.timedelta(seconds=duration_seconds)
            started = started_dt.isoformat()
            finished = finished_dt.isoformat()
            updated = finished_dt
            status = "completed"
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
                    status,
                    50,
                    created.isoformat(),
                    updated.isoformat() if hasattr(updated, "isoformat") else str(updated),
                    created.isoformat(),
                    started,
                    finished,
                    f"/tmp/{job_id}",
                ),
            )
        finally:
            conn.close()

    def insert_snapshot(
        self,
        when,
        *,
        pending=0,
        retry=0,
        processing=0,
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
                    processing,
                    retry,
                    0,
                    0,
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

    def seed_six_fresh_snapshots(self, *, pending=4, active=1, known=1):
        for index in range(6):
            self.insert_snapshot(
                NOW - dt.timedelta(minutes=(5 - index) * 10),
                pending=pending,
                active=active,
                known=known,
            )

    def seed_completed_jobs(self, count=3, duration_seconds=600):
        for index in range(count):
            self.insert_job(
                f"done-{index}",
                created=NOW - dt.timedelta(minutes=100 - index * 10),
                duration_seconds=duration_seconds,
            )

    def test_current_worker_capacity_clears_queue_in_nominal_and_p95_models(self):
        self.seed_six_fresh_snapshots(pending=4, active=1)
        self.seed_completed_jobs(count=3, duration_seconds=600)
        self.insert_job("queued-1", created=NOW - dt.timedelta(minutes=20))

        with patch.dict(os.environ, FORECAST_ENV, clear=False):
            result = history.build_capacity_forecast(now=NOW)

        self.assertTrue(result["modelAvailable"])
        self.assertEqual(result["sample"]["arrivals"], 4)
        self.assertEqual(result["rates"]["arrivalPerHour"], 2.0)
        self.assertEqual(result["rates"]["nominalPerWorkerPerHour"], 6.0)
        self.assertEqual(result["rates"]["conservativePerWorkerPerHour"], 6.0)
        self.assertEqual(result["queue"]["backlogJobs"], 4)
        self.assertEqual(result["current"]["nominal"]["state"], "clearing")
        self.assertEqual(result["current"]["conservative"]["state"], "clearing")
        self.assertEqual(
            result["decision"]["state"],
            "current_capacity_clearing",
        )
        self.assertGreater(result["current"]["nominal"]["clearEtaSeconds"], 0)

    def test_plus_one_worker_can_restore_drain_when_arrivals_exceed_one_worker(self):
        self.seed_six_fresh_snapshots(pending=10, active=1)
        self.seed_completed_jobs(count=3, duration_seconds=600)
        for index in range(17):
            self.insert_job(
                f"burst-{index}",
                created=NOW - dt.timedelta(minutes=110 - index * 3),
            )

        with patch.dict(os.environ, FORECAST_ENV, clear=False):
            result = history.build_capacity_forecast(now=NOW)

        self.assertTrue(result["modelAvailable"])
        self.assertEqual(result["sample"]["arrivals"], 20)
        self.assertEqual(result["rates"]["arrivalPerHour"], 10.0)
        self.assertEqual(result["current"]["nominal"]["state"], "growing")
        self.assertEqual(result["plusOneWorker"]["conservative"]["state"], "clearing")
        self.assertEqual(
            result["decision"]["state"],
            "one_more_worker_would_restore_drain",
        )

    def test_open_dependency_incident_takes_priority_over_capacity_recommendation(self):
        self.seed_six_fresh_snapshots(pending=10, active=1)
        self.seed_completed_jobs(count=3, duration_seconds=600)
        for index in range(5):
            self.insert_job(
                f"queued-{index}",
                created=NOW - dt.timedelta(minutes=30 + index),
            )
        incidents.sync_operational_incidents(
            now=NOW - dt.timedelta(minutes=5),
            candidates=[{
                "incidentKey": "error_burst:r2_storage",
                "incidentType": "error_burst",
                "category": "storage",
                "severity": "critical",
                "title": "R2 storage failure",
                "detail": "R2 unavailable",
                "action": "repair R2",
                "errorCode": "R2_STORAGE",
                "resourceId": "R2_STORAGE",
            }],
        )

        with patch.dict(os.environ, FORECAST_ENV, clear=False):
            result = history.build_capacity_forecast(now=NOW)

        self.assertEqual(result["decision"]["state"], "dependency_blocked")
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["blockers"][0]["code"], "R2_STORAGE")

    def test_insufficient_samples_do_not_produce_second_worker_conclusion(self):
        self.insert_snapshot(NOW, pending=10, active=1)
        self.insert_job(
            "done-only",
            created=NOW - dt.timedelta(minutes=20),
            duration_seconds=600,
        )

        with patch.dict(os.environ, FORECAST_ENV, clear=False):
            result = history.build_capacity_forecast(now=NOW)

        self.assertFalse(result["modelAvailable"])
        self.assertEqual(result["decision"]["state"], "insufficient_data")
        self.assertEqual(result["current"]["nominal"]["state"], "unavailable")
        self.assertTrue(result["limitations"])

    def test_dashboard_includes_capacity_forecast_without_new_migration(self):
        self.seed_six_fresh_snapshots(pending=2, active=1)
        self.seed_completed_jobs(count=3, duration_seconds=600)
        with patch.dict(os.environ, FORECAST_ENV, clear=False):
            dashboard = history.build_operational_dashboard(window="24h", now=NOW)
        self.assertIn("capacityForecast", dashboard)
        self.assertIn("decision", dashboard["capacityForecast"])


if __name__ == "__main__":
    unittest.main()
