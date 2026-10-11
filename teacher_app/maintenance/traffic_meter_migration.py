"""Daily outbound-traffic counters and the alert-sent ledger (additive only)."""
from teacher_app.maintenance.migrations import migration


@migration("0119-traffic-meter")
def traffic_meter_119(conn, kind: str) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS traffic_usage (
        day TEXT NOT NULL,
        bucket TEXT NOT NULL,
        bytes BIGINT NOT NULL DEFAULT 0,
        requests BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (day, bucket)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS traffic_alerts (
        month TEXT NOT NULL,
        threshold_gb TEXT NOT NULL,
        sent_at TEXT NOT NULL DEFAULT '',
        total_bytes BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (month, threshold_gb)
    )""")
