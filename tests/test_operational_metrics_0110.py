import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from teacher_app.command_center.notification_routes import register_notification_state_routes
from teacher_app.common import db as common_db
from teacher_app.maintenance.operational_incident_migration import operational_incidents_108
from teacher_app.maintenance.operational_incident_response_migration import operational_incident_response_109
from teacher_app.maintenance.operational_metrics_migration import operational_metrics_history_110
from teacher_app.notifications import incidents
from teacher_app.operations import history
from teacher_app.worker import schema as worker_schema


NOW = dt.datetime(2026, 10, 3, 12, 0, tzinfo=dt.timezone.utc)
SYSTEM_USER = {
    "username": "sys1",
    "role": "system_admin",
    "roles": ["system_admin"],
}
LEARNER = {
    "username": "student1",
    "role": "student",
    "roles": ["student"],
}


class OperationalMetrics0110Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "operations.sqlite"

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

    def insert_job(self, job_id, status, started_at, finished_at):
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
                    started_at,
                    finished_at or started_at,
                    started_at,
                    started_at,
                    finished_at,
                    f"/tmp/{job_id}",
                ),
            )
        finally:
            conn.close()

    @staticmethod
    def status_payload(active_workers=1, available=True, pending=0, duration=120):
        workers = (
            [{"workerId": "worker-a", "status": "online"}]
            if active_workers
            else [{"workerId": "worker-a", "status": "offline"}]
        )
        return {
            "pendingJobs": pending,
            "processingJobs": 0,
            "retryJobs": 0,
            "failedJobs": 0,
            "oldestPendingAgeSeconds": 30 if pending else 0,
            "recentTerminalJobs": 2,
            "recentFailureRate": 0.5,
            "averageCompletedDurationSeconds": duration,
            "healthyProcessingJobs": 0,
            "heartbeatDelayedJobs": 0,
            "stalledJobs": 0,
            "workers": workers,
            "workerStatusAvailable": available,
        }

    @staticmethod
    def candidate():
        return {
            "incidentKey": "error_burst:r2_storage",
            "incidentType": "error_burst",
            "category": "storage",
            "severity": "critical",
            "title": "教材背景工作連續發生 R2_STORAGE",
            "detail": "最近已連續 3 筆失敗。",
            "action": "確認 R2 bucket 與網路。",
            "errorCode": "R2_STORAGE",
            "resourceId": "R2_STORAGE",
        }

    def test_snapshots_and_incident_history_build_truthful_24h_dashboard(self):
        self.insert_job(
            "previous-ok",
            "completed",
            (NOW - dt.timedelta(hours=30, minutes=1)).isoformat(),
            (NOW - dt.timedelta(hours=30)).isoformat(),
        )
        self.insert_job(
            "current-ok",
            "completed",
            (NOW - dt.timedelta(hours=2, minutes=2)).isoformat(),
            (NOW - dt.timedelta(hours=2)).isoformat(),
        )
        self.insert_job(
            "current-fail",
            "failed",
            (NOW - dt.timedelta(hours=1, minutes=1)).isoformat(),
            (NOW - dt.timedelta(hours=1)).isoformat(),
        )

        opened = incidents.sync_operational_incidents(
            now=NOW - dt.timedelta(minutes=20),
            candidates=[self.candidate()],
        )
        with patch.object(
            history.worker_operations,
            "status",
            return_value=self.status_payload(active_workers=1, pending=2, duration=120),
        ):
            history.record_operational_sample(
                now=NOW - dt.timedelta(minutes=20),
                lifecycle=opened,
            )

        resolved = incidents.sync_operational_incidents(
            now=NOW - dt.timedelta(minutes=10),
            candidates=[],
        )
        with patch.object(
            history.worker_operations,
            "status",
            return_value=self.status_payload(active_workers=0, pending=0, duration=120),
        ):
            history.record_operational_sample(
                now=NOW - dt.timedelta(minutes=10),
                lifecycle=resolved,
            )

        dashboard = history.build_operational_dashboard(window="24h", now=NOW)
        self.assertEqual(dashboard["window"], "24h")
        self.assertEqual(dashboard["dataCoverage"]["windowSampleCount"], 2)
        self.assertTrue(dashboard["dataCoverage"]["sampledHistoryAvailable"])
        self.assertEqual(dashboard["worker"]["observedAvailability"], 0.5)
        self.assertEqual(dashboard["queue"]["maxPendingJobs"], 2)

        self.assertEqual(dashboard["material"]["terminalJobs"], 2)
        self.assertEqual(dashboard["material"]["completedJobs"], 1)
        self.assertEqual(dashboard["material"]["failedJobs"], 1)
        self.assertEqual(dashboard["material"]["successRate"], 0.5)
        self.assertEqual(dashboard["material"]["averageDurationSeconds"], 120.0)
        self.assertEqual(dashboard["material"]["previousAverageDurationSeconds"], 60.0)
        self.assertEqual(dashboard["material"]["durationChangePercent"], 100.0)

        self.assertEqual(dashboard["incidents"]["opened"], 1)
        self.assertEqual(dashboard["incidents"]["resolved"], 1)
        self.assertEqual(dashboard["incidents"]["averageMttrSeconds"], 600.0)
        self.assertEqual(
            dashboard["incidents"]["topComponents"][0],
            {"code": "R2_STORAGE", "count": 1},
        )
        self.assertTrue(dashboard["series"])

    def test_incident_transition_history_survives_snapshot_failure(self):
        opened = incidents.sync_operational_incidents(
            now=NOW,
            candidates=[self.candidate()],
        )
        with patch.object(
            history.worker_operations,
            "status",
            side_effect=RuntimeError("status unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                history.record_operational_sample(now=NOW, lifecycle=opened)

        conn, _kind = self.connect()
        try:
            row = conn.execute(
                "SELECT event_type,error_code FROM operational_incident_events"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(dict(row)["event_type"], "opened")
        self.assertEqual(dict(row)["error_code"], "R2_STORAGE")

    def test_operational_metrics_api_is_system_admin_only(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")
        owner = SimpleNamespace(app=app, _current_user=lambda: SYSTEM_USER)
        register_notification_state_routes(owner)
        client = app.test_client()

        with patch(
            "teacher_app.command_center.notification_routes.operational_history.build_operational_dashboard",
            return_value={"window": "7d", "series": []},
        ) as dashboard:
            response = client.get("/api/operational-metrics?window=7d")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["window"], "7d")
        dashboard.assert_called_once_with(window="7d")

        learner_app = Flask(__name__)
        learner_app.config.update(TESTING=True, SECRET_KEY="test")
        learner_owner = SimpleNamespace(app=learner_app, _current_user=lambda: LEARNER)
        register_notification_state_routes(learner_owner)
        denied = learner_app.test_client().get("/api/operational-metrics?window=24h")
        self.assertEqual(denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()
