"""Additive history tables for operational SLO/trend reporting."""
from teacher_app.maintenance.migrations import _columns, _table_exists, migration


@migration("0110-operational-metrics-history")
def operational_metrics_history_110(conn, kind: str) -> None:
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_true = "TRUE" if kind == "postgres" else "1"
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS operational_metric_snapshots (
            id TEXT PRIMARY KEY,
            sampled_at TEXT NOT NULL,
            pending_jobs INTEGER NOT NULL DEFAULT 0,
            processing_jobs INTEGER NOT NULL DEFAULT 0,
            retry_jobs INTEGER NOT NULL DEFAULT 0,
            failed_jobs INTEGER NOT NULL DEFAULT 0,
            oldest_pending_age_seconds INTEGER NOT NULL DEFAULT 0,
            recent_terminal_jobs INTEGER NOT NULL DEFAULT 0,
            recent_failure_rate REAL NOT NULL DEFAULT 0,
            average_completed_duration_seconds REAL NOT NULL DEFAULT 0,
            healthy_processing_jobs INTEGER NOT NULL DEFAULT 0,
            heartbeat_delayed_jobs INTEGER NOT NULL DEFAULT 0,
            stalled_jobs INTEGER NOT NULL DEFAULT 0,
            active_workers INTEGER NOT NULL DEFAULT 0,
            known_workers INTEGER NOT NULL DEFAULT 0,
            worker_status_available {boolean} NOT NULL DEFAULT {default_true},
            open_incidents INTEGER NOT NULL DEFAULT 0,
            critical_incidents INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_operational_metric_snapshots_time "
        "ON operational_metric_snapshots(sampled_at)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS operational_incident_events (
            event_key TEXT PRIMARY KEY,
            incident_key TEXT NOT NULL,
            incident_type TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'operations',
            severity TEXT NOT NULL DEFAULT 'warning',
            error_code TEXT NOT NULL DEFAULT '',
            resource_id TEXT NOT NULL DEFAULT '',
            generation INTEGER NOT NULL DEFAULT 1,
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            opened_at TEXT NOT NULL DEFAULT '',
            resolved_at TEXT NOT NULL DEFAULT '',
            duration_seconds INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_operational_incident_events_time "
        "ON operational_incident_events(occurred_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_operational_incident_events_code "
        "ON operational_incident_events(error_code,event_type,occurred_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_operational_incident_events_incident "
        "ON operational_incident_events(incident_key,generation,event_type)"
    )
    if (
        _table_exists(conn, kind, "material_jobs")
        and "finished_at" in _columns(conn, kind, "material_jobs")
    ):
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_material_jobs_finished_at "
            "ON material_jobs(finished_at)"
        )


__all__ = ["operational_metrics_history_110"]
