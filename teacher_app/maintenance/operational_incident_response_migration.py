"""Additive response metadata for operational incident handling."""
from teacher_app.maintenance.migrations import _add_columns, migration


@migration("0109-operational-incident-response")
def operational_incident_response_109(conn, kind: str) -> None:
    _add_columns(
        conn,
        kind,
        "operational_incidents",
        {
            "response_state": "response_state TEXT NOT NULL DEFAULT 'unacknowledged'",
            "acknowledged_by": "acknowledged_by TEXT NOT NULL DEFAULT ''",
            "acknowledged_at": "acknowledged_at TEXT NOT NULL DEFAULT ''",
            "assigned_to": "assigned_to TEXT NOT NULL DEFAULT ''",
            "maintenance_until": "maintenance_until TEXT NOT NULL DEFAULT ''",
            "response_note": "response_note TEXT NOT NULL DEFAULT ''",
            "response_updated_by": "response_updated_by TEXT NOT NULL DEFAULT ''",
            "response_updated_at": "response_updated_at TEXT NOT NULL DEFAULT ''",
        },
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_operational_incidents_response "
        "ON operational_incidents(status,response_state,maintenance_until)"
    )


__all__ = ["operational_incident_response_109"]
