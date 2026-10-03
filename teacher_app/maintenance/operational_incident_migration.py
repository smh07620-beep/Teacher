"""Persist de-duplicated operational incident lifecycle state."""
from teacher_app.maintenance.migrations import migration


@migration("0108-operational-incidents")
def operational_incidents_108(conn, kind: str) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS operational_incidents (
            incident_key TEXT PRIMARY KEY,
            incident_type TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'operations',
            severity TEXT NOT NULL DEFAULT 'warning',
            status TEXT NOT NULL DEFAULT 'open',
            title TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT '',
            resource_id TEXT NOT NULL DEFAULT '',
            generation INTEGER NOT NULL DEFAULT 1,
            occurrence_count INTEGER NOT NULL DEFAULT 1,
            opened_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            resolved_at TEXT NOT NULL DEFAULT ''
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_operational_incidents_status "
        "ON operational_incidents(status,last_seen_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_operational_incidents_type "
        "ON operational_incidents(incident_type,status,last_seen_at)"
    )


__all__ = ["operational_incidents_108"]
