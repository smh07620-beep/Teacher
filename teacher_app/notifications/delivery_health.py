"""Read-only email notification delivery health for system administrators."""
from __future__ import annotations
import datetime as dt
from teacher_app.common import db as common_db

def build_email_delivery_health(*, now: dt.datetime | None = None) -> dict:
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT status,COUNT(*) AS cnt FROM email_delivery_attempts WHERE attempted_at>={ph} GROUP BY status",
            (start.isoformat(),),
        ).fetchall()
        latest = conn.execute(
            "SELECT attempted_at,status,kind,error_type FROM email_delivery_attempts ORDER BY attempted_at DESC LIMIT 1"
        ).fetchone()
    counts = {str(dict(row).get("status") or ""): int(dict(row).get("cnt", 0) or 0) for row in rows}
    last = dict(latest) if latest else {}
    return {
        "generatedAt": current.isoformat(),
        "today": {"sent": counts.get("sent", 0), "failed": counts.get("failed", 0), "attempted": sum(counts.values())},
        "lastDeliveryAt": str(last.get("attempted_at") or ""),
        "lastStatus": str(last.get("status") or ""),
        "lastKind": str(last.get("kind") or ""),
        "lastErrorType": str(last.get("error_type") or ""),
    }

__all__=["build_email_delivery_health"]
