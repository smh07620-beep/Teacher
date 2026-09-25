"""Release migration for per-user notification read state."""
from __future__ import annotations

from teacher_app.maintenance.migrations import migration


@migration("0086-notification-read-state")
def notification_read_state_86(conn, kind: str) -> None:
    """Persist only read markers; notification content stays canonical elsewhere."""
    del kind
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notification_read_state ("
        "username TEXT NOT NULL,notification_key TEXT NOT NULL,"
        "read_at TEXT NOT NULL,updated_at TEXT NOT NULL,"
        "PRIMARY KEY(username,notification_key))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_read_state_user_updated "
        "ON notification_read_state(username,updated_at)"
    )


__all__ = ["notification_read_state_86"]
