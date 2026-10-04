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
        latest_run = conn.execute(
            "SELECT id,started_at,completed_at,expected_events,claimed_events,sent_events,failed_events,status,error_type FROM email_reminder_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    counts = {str(dict(row).get("status") or ""): int(dict(row).get("cnt", 0) or 0) for row in rows}
    last = dict(latest) if latest else {}
    run = dict(latest_run) if latest_run else {}
    local_now = current.astimezone(dt.timezone(dt.timedelta(hours=8)))
    local_run = None
    if run.get("started_at"):
        try:
            local_run = dt.datetime.fromisoformat(str(run["started_at"]).replace("Z","+00:00")).astimezone(dt.timezone(dt.timedelta(hours=8)))
        except ValueError:
            local_run = None
    scheduled_due = local_now.hour > 9 or (local_now.hour == 9 and local_now.minute >= 45)
    ran_today = bool(local_run and local_run.date() == local_now.date())
    expected = int(run.get("expected_events",0) or 0) if ran_today else 0
    sent_events = int(run.get("sent_events",0) or 0) if ran_today else 0
    failed_events = int(run.get("failed_events",0) or 0) if ran_today else 0
    health = "healthy"
    issue = ""
    if scheduled_due and not ran_today:
        health, issue = "missing_run", "今日提醒排程應已執行，但尚未找到執行紀錄。"
    elif ran_today and str(run.get("status") or "") in {"running","failed","partial"}:
        health, issue = "delivery_issue", "今日提醒排程未完整完成，請檢查寄送設定或執行紀錄。"
    elif ran_today and expected > sent_events + failed_events + int(run.get("claimed_events",0) or 0):
        health, issue = "delivery_gap", "預計提醒與實際處理數量不一致。"
    return {
        "generatedAt": current.isoformat(),
        "today": {"sent": counts.get("sent", 0), "failed": counts.get("failed", 0), "attempted": sum(counts.values())},
        "lastDeliveryAt": str(last.get("attempted_at") or ""),
        "lastStatus": str(last.get("status") or ""),
        "lastKind": str(last.get("kind") or ""),
        "lastErrorType": str(last.get("error_type") or ""),
        "schedule": {
            "health": health, "issue": issue, "ranToday": ran_today, "scheduledDue": scheduled_due,
            "lastRunAt": str(run.get("started_at") or ""), "lastRunStatus": str(run.get("status") or ""),
            "expectedEvents": expected, "claimedEvents": int(run.get("claimed_events",0) or 0) if ran_today else 0,
            "sentEvents": sent_events, "failedEvents": failed_events,
        },
    }

__all__=["build_email_delivery_health"]
