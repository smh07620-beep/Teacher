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
        original_name="material.pdf",
        source_bytes=1024 * 1024,
        result=None,
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
                    started_at,finished_at,staging_path,original_name,source_bytes,result
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
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
                    original_name,
                    source_bytes,
                    __import__("json").dumps(result or {}, ensure_ascii=False),
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

    def test_workload_calibration_separates_documents_and_media_cost(self):
        self.seed_six_fresh_snapshots(pending=2, active=1)

        for index in range(2):
            self.insert_job(
                f"doc-{index}",
                created=NOW - dt.timedelta(minutes=100 - index * 10),
                duration_seconds=60,
                original_name=f"doc-{index}.pdf",
                source_bytes=5 * 1024 * 1024,
                result={"pageCount": 10, "storageMeta": {}},
            )
            self.insert_job(
                f"media-{index}",
                created=NOW - dt.timedelta(minutes=80 - index * 10),
                duration_seconds=1800,
                original_name=f"media-{index}.mp4",
                source_bytes=200 * 1024 * 1024,
                result={
                    "pageCount": 0,
                    "storageMeta": {
                        "mediaKind": "video",
                        "durationSeconds": 3600,
                        "transcodeMode": "transcode",
                    },
                },
            )

        with patch.dict(os.environ, {
            **FORECAST_ENV,
            "OPERATIONS_FORECAST_MIN_WORKLOAD_COMPLETED_JOBS": "2",
        }, clear=False):
            workload = history.build_workload_calibration(
                now=NOW,
                window_hours=2,
                current_active_workers=1,
            )

        self.assertTrue(workload["available"])
        self.assertTrue(workload["fullyCalibrated"])
        profiles = {row["kind"]: row for row in workload["profiles"]}
        self.assertEqual(profiles["document"]["medianDurationSeconds"], 60.0)
        self.assertEqual(profiles["document"]["medianPageCount"], 10.0)
        self.assertEqual(profiles["document"]["medianSecondsPerPage"], 6.0)
        self.assertEqual(profiles["media"]["medianDurationSeconds"], 1800.0)
        self.assertEqual(profiles["media"]["medianMediaDurationSeconds"], 3600.0)
        self.assertEqual(profiles["media"]["medianProcessingToMediaRatio"], 0.5)
        self.assertGreater(
            profiles["media"]["medianDurationSeconds"],
            profiles["document"]["medianDurationSeconds"] * 20,
        )
        self.assertGreater(workload["conservativeWorkerDemand"], 0)

    def test_uncalibrated_media_backlog_disables_mixed_workload_eta(self):
        self.seed_six_fresh_snapshots(pending=2, active=1)
        for index in range(2):
            self.insert_job(
                f"doc-{index}",
                created=NOW - dt.timedelta(minutes=90 - index * 10),
                duration_seconds=60,
                original_name=f"doc-{index}.pdf",
                result={"pageCount": 10},
            )
        self.insert_job(
            "queued-video",
            created=NOW - dt.timedelta(minutes=5),
            original_name="long-video.mp4",
            source_bytes=500 * 1024 * 1024,
        )

        with patch.dict(os.environ, {
            **FORECAST_ENV,
            "OPERATIONS_FORECAST_MIN_WORKLOAD_COMPLETED_JOBS": "2",
        }, clear=False):
            workload = history.build_workload_calibration(
                now=NOW,
                window_hours=2,
                current_active_workers=1,
            )

        self.assertFalse(workload["fullyCalibrated"])
        self.assertEqual(workload["uncalibratedBacklogJobs"], 1)
        self.assertEqual(workload["current"]["nominal"]["state"], "unavailable")
        media = next(row for row in workload["profiles"] if row["kind"] == "media")
        self.assertFalse(media["calibrated"])
        self.assertEqual(media["backlogJobs"], 1)

    def test_capacity_forecast_embeds_workload_profiles(self):
        self.seed_six_fresh_snapshots(pending=1, active=1)
        for index in range(2):
            self.insert_job(
                f"doc-{index}",
                created=NOW - dt.timedelta(minutes=80 - index * 10),
                duration_seconds=120,
                original_name=f"slides-{index}.pptx",
                source_bytes=15 * 1024 * 1024,
                result={"pageCount": 20, "storageMeta": {}},
            )
        self.insert_job(
            "queued-doc",
            created=NOW - dt.timedelta(minutes=5),
            original_name="new.pdf",
        )
        with patch.dict(os.environ, {
            **FORECAST_ENV,
            "OPERATIONS_FORECAST_MIN_COMPLETED_JOBS": "2",
            "OPERATIONS_FORECAST_MIN_WORKLOAD_COMPLETED_JOBS": "2",
        }, clear=False):
            forecast = history.build_capacity_forecast(now=NOW)
        self.assertIn("workloadCalibration", forecast)
        profile = forecast["workloadCalibration"]["profiles"][0]
        self.assertEqual(profile["kind"], "document")
        self.assertTrue(profile["calibrated"])
        self.assertTrue(profile["sizeBands"])

    def test_peak_what_if_uses_pages_and_media_duration_calibration(self):
        self.seed_six_fresh_snapshots(pending=0, active=1)

        for index in range(2):
            self.insert_job(
                f"doc-whatif-{index}",
                created=NOW - dt.timedelta(minutes=100 - index * 10),
                duration_seconds=60,
                original_name=f"doc-whatif-{index}.pdf",
                source_bytes=5 * 1024 * 1024,
                result={"pageCount": 10, "storageMeta": {}},
            )
            self.insert_job(
                f"media-whatif-{index}",
                created=NOW - dt.timedelta(minutes=80 - index * 10),
                duration_seconds=1800,
                original_name=f"media-whatif-{index}.mp4",
                source_bytes=200 * 1024 * 1024,
                result={
                    "pageCount": 0,
                    "storageMeta": {
                        "mediaKind": "video",
                        "durationSeconds": 3600,
                        "transcodeMode": "transcode",
                    },
                },
            )

        with patch.dict(os.environ, {
            **FORECAST_ENV,
            "OPERATIONS_FORECAST_MIN_COMPLETED_JOBS": "3",
            "OPERATIONS_FORECAST_MIN_WORKLOAD_COMPLETED_JOBS": "2",
        }, clear=False):
            result = history.simulate_capacity_what_if(
                {
                    "documentCount": 10,
                    "documentPages": 20,
                    "mediaCount": 3,
                    "mediaMinutes": 30,
                },
                now=NOW,
            )

        self.assertTrue(result["available"])
        components = {row["kind"]: row for row in result["components"]}
        self.assertEqual(components["document"]["method"], "pages")
        self.assertEqual(
            components["document"]["nominalServiceSecondsEach"],
            120.0,
        )
        self.assertEqual(components["media"]["method"], "media_duration")
        self.assertEqual(
            components["media"]["nominalServiceSecondsEach"],
            900.0,
        )
        self.assertEqual(result["peakBacklogJobs"], 13)
        self.assertEqual(result["bottleneck"]["kind"], "media")
        self.assertGreater(result["oneWorker"]["nominal"]["clearEtaSeconds"], 0)
        self.assertLess(
            result["twoWorkers"]["nominal"]["clearEtaSeconds"],
            result["oneWorker"]["nominal"]["clearEtaSeconds"],
        )

    def test_peak_what_if_refuses_eta_when_requested_media_is_uncalibrated(self):
        self.seed_six_fresh_snapshots(pending=0, active=1)
        for index in range(3):
            self.insert_job(
                f"doc-only-{index}",
                created=NOW - dt.timedelta(minutes=90 - index * 10),
                duration_seconds=60,
                original_name=f"doc-only-{index}.pdf",
                result={"pageCount": 10, "storageMeta": {}},
            )

        with patch.dict(os.environ, {
            **FORECAST_ENV,
            "OPERATIONS_FORECAST_MIN_WORKLOAD_COMPLETED_JOBS": "2",
        }, clear=False):
            result = history.simulate_capacity_what_if(
                {
                    "documentCount": 0,
                    "mediaCount": 3,
                    "mediaMinutes": 30,
                },
                now=NOW,
            )

        self.assertFalse(result["available"])
        self.assertEqual(result["oneWorker"]["nominal"]["state"], "unavailable")
        media = next(row for row in result["components"] if row["kind"] == "media")
        self.assertFalse(media["calibrated"])
        self.assertTrue(
            any("影音" in text for text in result["limitations"])
        )

    def test_peak_what_if_bounds_untrusted_query_values(self):
        self.seed_six_fresh_snapshots(pending=0, active=1)
        for index in range(2):
            self.insert_job(
                f"doc-bound-{index}",
                created=NOW - dt.timedelta(minutes=90 - index * 10),
                duration_seconds=60,
                original_name=f"doc-bound-{index}.pdf",
                result={"pageCount": 10, "storageMeta": {}},
            )

        with patch.dict(os.environ, {
            **FORECAST_ENV,
            "OPERATIONS_FORECAST_MIN_WORKLOAD_COMPLETED_JOBS": "2",
        }, clear=False):
            result = history.simulate_capacity_what_if(
                {
                    "documentCount": 9999,
                    "documentPages": 9999,
                    "mediaCount": -3,
                    "mediaMinutes": 9999,
                    "imageCount": -1,
                    "archiveCount": 9999,
                },
                now=NOW,
            )

        self.assertEqual(result["scenario"]["documentCount"], 100)
        self.assertEqual(result["scenario"]["documentPages"], 500)
        self.assertEqual(result["scenario"]["mediaCount"], 0)
        self.assertEqual(result["scenario"]["mediaMinutes"], 240)
        self.assertEqual(result["scenario"]["imageCount"], 0)
        self.assertEqual(result["scenario"]["archiveCount"], 50)

    def test_dashboard_includes_capacity_forecast_without_new_migration(self):
        self.seed_six_fresh_snapshots(pending=2, active=1)
        self.seed_completed_jobs(count=3, duration_seconds=600)
        with patch.dict(os.environ, FORECAST_ENV, clear=False):
            dashboard = history.build_operational_dashboard(window="24h", now=NOW)
        self.assertIn("capacityForecast", dashboard)
        self.assertIn("decision", dashboard["capacityForecast"])


if __name__ == "__main__":
    unittest.main()
