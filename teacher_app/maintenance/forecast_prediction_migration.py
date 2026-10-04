"""Additive persistence for pre-completion forecast predictions and backtests."""
from teacher_app.maintenance.migrations import migration


@migration("0111-forecast-prediction-calibration")
def forecast_prediction_calibration_111(conn, kind: str) -> None:
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_false = "FALSE" if kind == "postgres" else "0"
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS operational_forecast_predictions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL UNIQUE,
            workload_kind TEXT NOT NULL DEFAULT 'other',
            size_band TEXT NOT NULL DEFAULT '',
            model_basis TEXT NOT NULL DEFAULT 'class_duration',
            model_version TEXT NOT NULL DEFAULT 'workload-v1',
            sample_count INTEGER NOT NULL DEFAULT 0,
            predicted_nominal_seconds REAL NOT NULL DEFAULT 0,
            predicted_p95_seconds REAL NOT NULL DEFAULT 0,
            predicted_at TEXT NOT NULL,
            evaluation_status TEXT NOT NULL DEFAULT 'pending',
            completed_at TEXT NOT NULL DEFAULT '',
            actual_seconds REAL NOT NULL DEFAULT 0,
            nominal_absolute_error_seconds REAL NOT NULL DEFAULT 0,
            nominal_absolute_percentage_error REAL NOT NULL DEFAULT 0,
            nominal_signed_percentage_error REAL NOT NULL DEFAULT 0,
            p95_covered {boolean} NOT NULL DEFAULT {default_false},
            evaluated_at TEXT NOT NULL DEFAULT ''
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_operational_forecast_predictions_status "
        "ON operational_forecast_predictions(evaluation_status,predicted_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_operational_forecast_predictions_completed "
        "ON operational_forecast_predictions(completed_at,workload_kind)"
    )


__all__ = ["forecast_prediction_calibration_111"]
