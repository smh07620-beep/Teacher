"""Durable email delivery attempts for system-admin observability."""
from teacher_app.maintenance.migrations import migration

@migration("0112-email-delivery-observability")
def email_delivery_observability_112(conn, kind: str) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS email_delivery_attempts (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        username TEXT NOT NULL,
        notification_key TEXT NOT NULL,
        kind TEXT NOT NULL,
        status TEXT NOT NULL,
        attempted_at TEXT NOT NULL,
        error_type TEXT NOT NULL DEFAULT ''
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_delivery_attempts_time ON email_delivery_attempts(attempted_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_delivery_attempts_status ON email_delivery_attempts(status,attempted_at)")

__all__=["email_delivery_observability_112"]
