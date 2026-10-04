import datetime as dt
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.common import db as common_db
from teacher_app.maintenance.forecast_prediction_migration import (
    forecast_prediction_calibration_111,
)
from teacher_app.maintenance.operational_incident_migration import (
    operational_incidents_108,
)
from teacher_app.maintenance.operational_incident_response_migration import (
    operational_incident_response_109,
)
from teacher_app.maintenance.operational_metrics_migration import (
    operational_metrics_history_110,
)
from teacher_app.operations import history
from teacher_app.worker import schema as worker_schema


NOW = dt.datetime(2026, 10, 4, 12, 0, tzinfo=dt.timezone.utc)


class ForecastPredictionCalibration0111Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "prediction.sqlite"

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
            forecast_prediction_calibration_111(conn, kind)
        finally:
            conn.close()
        patcher = patch.object(common_db, "get_connection", side_effect=self.connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def insert_job(
        self,
        job_id,
        *,
        status,
        created,
        started="",
        finished="",
        original_name="material.pdf",
        source_bytes=1024 * 1024,
        result="{}",
    ):
        conn, _kind = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO material_jobs(
                    id,status,priority,created_at,updated_at,available_at,
                    started_at,finished_at,staging_path,original_name,
                    source_bytes,result
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job_id,
                    status,
                    50,
                    created.isoformat(),
                    (finished or created.isoformat()),
                    created.isoformat(),
                    started,
                    finished,
                    f"/tmp/{job_id}",
                    original_name,
                    source_bytes,
                    result,
                ),
            )
        finally:
            conn.close()

    def seed_document_history(self):
        for index, seconds in enumerate((60, 80, 100)):
            created = NOW - dt.timedelta(hours=2, minutes=index * 10)
            started = created + dt.timedelta(minutes=1)
            finished = started + dt.timedelta(seconds=seconds)
            self.insert_job(
                f"history-{index}",
                status="completed",
                created=created,
                started=started.isoformat(),
                finished=finished.isoformat(),
                original_name=f"history-{index}.pdf",
                source_bytes=5 * 1024 * 1024,
                result='{"pageCount":10,"storageMeta":{}}',
            )

    def seed_snapshot(self):
        conn, _kind = self.connect()
        try:
            for index in range(6):
                when = NOW - dt.timedelta(minutes=(5 - index) * 10)
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
                        1,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        80,
                        0,
                        0,
                        0,
                        1,
                        1,
                        1,
                        0,
                        0,
                    ),
                )
        finally:
            conn.close()

    def test_0111_migration_is_idempotent_and_private_to_operational_history(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            forecast_prediction_calibration_111(conn, "sqlite")
            forecast_prediction_calibration_111(conn, "sqlite")
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("operational_forecast_predictions", tables)
            columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(operational_forecast_predictions)"
                ).fetchall()
            }
            for expected in (
                "job_id",
                "workload_kind",
                "predicted_nominal_seconds",
                "predicted_p95_seconds",
                "actual_seconds",
                "nominal_absolute_percentage_error",
                "p95_covered",
            ):
                self.assertIn(expected, columns)
        finally:
            conn.close()

    def test_precompletion_prediction_is_immutable_and_scored_after_completion(self):
        self.seed_document_history()
        created = NOW - dt.timedelta(minutes=5)
        self.insert_job(
            "future-job",
            status="queued",
            created=created,
            original_name="future.pdf",
            source_bytes=5 * 1024 * 1024,
        )
        with patch.dict(
            os.environ,
            {"OPERATIONS_FORECAST_MIN_WORKLOAD_COMPLETED_JOBS": "2"},
            clear=False,
        ):
            first = history.record_forecast_prediction_for_job(
                {
                    "id": "future-job",
                    "originalName": "future.pdf",
                    "sourceBytes": 5 * 1024 * 1024,
                },
                now=NOW,
            )
            second = history.record_forecast_prediction_for_job(
                {
                    "id": "future-job",
                    "originalName": "future.pdf",
                    "sourceBytes": 5 * 1024 * 1024,
                },
                now=NOW + dt.timedelta(minutes=1),
            )
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(second["reason"], "exists")

        conn, _kind = self.connect()
        try:
            predicted = dict(
                conn.execute(
                    "SELECT * FROM operational_forecast_predictions "
                    "WHERE job_id='future-job'"
                ).fetchone()
            )
            started = NOW + dt.timedelta(minutes=2)
            finished = started + dt.timedelta(seconds=160)
            conn.execute(
                """
                UPDATE material_jobs
                SET status='completed',started_at=?,finished_at=?,updated_at=?
                WHERE id='future-job'
                """,
                (
                    started.isoformat(),
                    finished.isoformat(),
                    finished.isoformat(),
                ),
            )
        finally:
            conn.close()

        result = history.reconcile_forecast_predictions(
            now=NOW + dt.timedelta(minutes=6)
        )
        self.assertEqual(result["evaluated"], 1)

        conn, _kind = self.connect()
        try:
            scored = dict(
                conn.execute(
                    "SELECT * FROM operational_forecast_predictions "
                    "WHERE job_id='future-job'"
                ).fetchone()
            )
        finally:
            conn.close()

        self.assertEqual(scored["evaluation_status"], "evaluated")
        self.assertEqual(scored["predicted_at"], predicted["predicted_at"])
        self.assertEqual(scored["predicted_nominal_seconds"], 80.0)
        self.assertEqual(scored["actual_seconds"], 160.0)
        self.assertEqual(scored["nominal_absolute_error_seconds"], 80.0)
        self.assertAlmostEqual(
            scored["nominal_absolute_percentage_error"],
            0.5,
            places=6,
        )
        self.assertAlmostEqual(
            scored["nominal_signed_percentage_error"],
            -0.5,
            places=6,
        )
        self.assertEqual(scored["p95_covered"], 0)

    def test_accuracy_summary_reports_bias_and_p95_coverage(self):
        conn, _kind = self.connect()
        try:
            rows = [
                ("a", "document", 100, 140, 200, 100, 0.5, -0.5, 0),
                ("b", "document", 100, 180, 100, 0, 0.0, 0.0, 1),
                ("c", "media", 300, 600, 450, 150, 0.333333, -0.333333, 1),
            ]
            for job_id, kind, pred, p95, actual, abs_err, ape, signed, covered in rows:
                conn.execute(
                    """
                    INSERT INTO operational_forecast_predictions(
                        id,job_id,workload_kind,size_band,model_basis,model_version,
                        sample_count,predicted_nominal_seconds,predicted_p95_seconds,
                        predicted_at,evaluation_status,completed_at,actual_seconds,
                        nominal_absolute_error_seconds,
                        nominal_absolute_percentage_error,
                        nominal_signed_percentage_error,p95_covered,evaluated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "service:" + job_id,
                        job_id,
                        kind,
                        "small",
                        "class_duration",
                        "workload-v1",
                        3,
                        pred,
                        p95,
                        (NOW - dt.timedelta(hours=1)).isoformat(),
                        "evaluated",
                        NOW.isoformat(),
                        actual,
                        abs_err,
                        ape,
                        signed,
                        covered,
                        NOW.isoformat(),
                    ),
                )
        finally:
            conn.close()

        with patch.dict(
            os.environ,
            {"OPERATIONS_FORECAST_ACCURACY_MIN_EVALUATED": "3"},
            clear=False,
        ):
            accuracy = history.build_forecast_accuracy(now=NOW)

        self.assertEqual(accuracy["evaluated"], 3)
        self.assertEqual(accuracy["state"], "caution")
        self.assertEqual(accuracy["confidenceAdjustment"], "downgrade_one")
        self.assertAlmostEqual(
            accuracy["p95Coverage"],
            2 / 3,
            places=4,
        )
        self.assertEqual(accuracy["bias"], "optimistic")
        kinds = {row["kind"] for row in accuracy["workloads"]}
        self.assertEqual(kinds, {"document", "media"})

    def test_stable_backtest_does_not_upgrade_sparse_forecast_confidence(self):
        stable = {
            "available": True,
            "state": "stable",
            "label": "近期回測誤差穩定",
            "evaluated": 12,
            "pending": 0,
            "confidenceAdjustment": "none",
            "workloads": [],
        }
        snapshots = [
            {
                "sampled_at": (
                    NOW - dt.timedelta(minutes=(5 - index) * 10)
                ).isoformat(),
                "worker_status_available": 1,
                "active_workers": 1,
                "pending_jobs": 1,
                "retry_jobs": 0,
                "processing_jobs": 0,
            }
            for index in range(6)
        ]
        with patch.object(
            history,
            "_job_arrival_count",
            return_value=(4, True),
        ), patch.object(
            history,
            "_completed_durations",
            return_value=[60.0, 80.0, 100.0],
        ), patch.object(
            history,
            "_snapshot_rows_since",
            return_value=snapshots,
        ), patch.object(
            history,
            "_open_capacity_blockers",
            return_value=[],
        ), patch.object(
            history,
            "build_workload_calibration",
            return_value={"profiles": [], "fullyCalibrated": False},
        ), patch.object(
            history,
            "build_forecast_accuracy",
            return_value=stable,
        ), patch.dict(
            os.environ,
            {
                "OPERATIONS_FORECAST_WINDOW_HOURS": "2",
                "OPERATIONS_FORECAST_MIN_COMPLETED_JOBS": "3",
                "OPERATIONS_FORECAST_MIN_SNAPSHOT_COVERAGE": "0.5",
            },
            clear=False,
        ):
            forecast = history.build_capacity_forecast(now=NOW)

        self.assertEqual(forecast["rawConfidence"], "medium")
        self.assertEqual(forecast["confidence"], "medium")

    def test_real_backtest_can_only_lower_existing_forecast_confidence(self):
        high_error = {
            "available": True,
            "state": "low_trust",
            "label": "近期回測誤差偏高，Forecast 信心降至低",
            "evaluated": 7,
            "pending": 1,
            "confidenceAdjustment": "downgrade_to_low",
            "workloads": [],
        }
        snapshots = [
            {
                "sampled_at": (
                    NOW - dt.timedelta(minutes=(11 - index) * 10)
                ).isoformat(),
                "worker_status_available": 1,
                "active_workers": 1,
                "pending_jobs": 1,
                "retry_jobs": 0,
                "processing_jobs": 0,
            }
            for index in range(12)
        ]
        with patch.object(
            history,
            "_job_arrival_count",
            return_value=(6, True),
        ), patch.object(
            history,
            "_completed_durations",
            return_value=[60.0, 70.0, 80.0, 90.0, 100.0],
        ), patch.object(
            history,
            "_snapshot_rows_since",
            return_value=snapshots,
        ), patch.object(
            history,
            "_open_capacity_blockers",
            return_value=[],
        ), patch.object(
            history,
            "build_workload_calibration",
            return_value={"profiles": [], "fullyCalibrated": False},
        ), patch.object(
            history,
            "build_forecast_accuracy",
            return_value=high_error,
        ), patch.dict(
            os.environ,
            {
                "OPERATIONS_FORECAST_WINDOW_HOURS": "2",
                "OPERATIONS_FORECAST_MIN_COMPLETED_JOBS": "3",
                "OPERATIONS_FORECAST_MIN_SNAPSHOT_COVERAGE": "0.5",
            },
            clear=False,
        ):
            forecast = history.build_capacity_forecast(now=NOW)

        self.assertEqual(forecast["rawConfidence"], "high")
        self.assertEqual(forecast["confidence"], "low")
        self.assertIs(
            forecast["predictionCalibration"],
            high_error,
        )
        self.assertTrue(
            any("回測誤差" in text for text in forecast["limitations"])
        )


if __name__ == "__main__":
    unittest.main()
