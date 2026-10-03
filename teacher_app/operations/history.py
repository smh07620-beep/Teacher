"""Historical operational samples and truthful SLO/trend projections."""
from __future__ import annotations

import datetime as dt
import math
import os
from collections import Counter
from statistics import mean
from typing import Any, Iterable, Mapping

from teacher_app.common import db as common_db
from teacher_app.worker import operations as worker_operations


def _utc(value: dt.datetime | None = None) -> dt.datetime:
    current = value or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    return current.astimezone(dt.timezone.utc)


def _parse_time(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _optional_float(name: str) -> float | None:
    text = str(os.environ.get(name, "") or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.environ.get(name, default) or default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(str(os.environ.get(name, default) or default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _percentile(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _window_hours(value: str) -> int:
    return 168 if str(value or "").lower() == "7d" else 24


def _bucket_start(value: dt.datetime, *, hours: int) -> dt.datetime:
    value = value.astimezone(dt.timezone.utc)
    if hours <= 24:
        return value.replace(minute=0, second=0, microsecond=0)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _incident_event(
    item: Mapping[str, Any],
    event_type: str,
    occurred_at: dt.datetime,
) -> dict[str, Any]:
    opened = _parse_time(item.get("openedAt")) or occurred_at
    resolved = _parse_time(item.get("resolvedAt"))
    duration = (
        max(0, int((resolved - opened).total_seconds()))
        if event_type == "resolved" and resolved
        else 0
    )
    generation = max(1, int(item.get("generation") or 1))
    incident_key = str(item.get("incidentKey") or "")[:240]
    return {
        "event_key": f"{incident_key}:{generation}:{event_type}",
        "incident_key": incident_key,
        "incident_type": str(item.get("incidentType") or "")[:80],
        "category": str(item.get("category") or "operations")[:80],
        "severity": str(item.get("severity") or "warning")[:32],
        "error_code": str(item.get("errorCode") or "")[:120],
        "resource_id": str(item.get("resourceId") or "")[:240],
        "generation": generation,
        "event_type": event_type,
        "occurred_at": occurred_at.isoformat(),
        "opened_at": opened.isoformat(),
        "resolved_at": resolved.isoformat() if resolved else "",
        "duration_seconds": duration,
    }


def _write_incident_event(conn, kind: str, event: Mapping[str, Any]) -> None:
    ph = common_db.placeholder(kind)
    columns = tuple(event.keys())
    conn.execute(
        f"DELETE FROM operational_incident_events WHERE event_key={ph}",
        (event["event_key"],),
    )
    conn.execute(
        f"INSERT INTO operational_incident_events({','.join(columns)}) "
        f"VALUES ({','.join([ph] * len(columns))})",
        tuple(event[column] for column in columns),
    )


def _record_incident_transitions(
    lifecycle: Mapping[str, Any] | None,
    *,
    now: dt.datetime,
) -> None:
    if not lifecycle:
        return
    with common_db.transaction() as (conn, kind):
        for item in lifecycle.get("opened") or []:
            _write_incident_event(conn, kind, _incident_event(item, "opened", now))
        for item in lifecycle.get("reopened") or []:
            _write_incident_event(conn, kind, _incident_event(item, "opened", now))
        for item in lifecycle.get("resolved") or []:
            _write_incident_event(conn, kind, _incident_event(item, "resolved", now))


def record_operational_sample(
    *,
    now: dt.datetime | None = None,
    lifecycle: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Record one idempotent ten-minute sample and incident transition history."""
    current = _utc(now)
    _record_incident_transitions(lifecycle, now=current)
    bucket_minute = (current.minute // 10) * 10
    sampled = current.replace(minute=bucket_minute, second=0, microsecond=0)
    status = worker_operations.status(
        lambda: {"backend": "metrics", "available": True, "shared": True}
    )
    workers = list(status.get("workers") or [])
    active_workers = sum(
        str(worker.get("status") or "") in {"online", "busy"}
        for worker in workers
    )

    with common_db.read_connection() as (read_conn, _kind):
        row = read_conn.execute(
            "SELECT COUNT(*) AS count,"
            "SUM(CASE WHEN severity='critical' THEN 1 ELSE 0 END) AS critical "
            "FROM operational_incidents WHERE status='open'"
        ).fetchone()
        raw = dict(row) if row else {}
        open_incidents = int(raw.get("count") or 0)
        critical_incidents = int(raw.get("critical") or 0)

    snapshot = {
        "id": f"ops:{sampled.isoformat()}",
        "sampled_at": sampled.isoformat(),
        "pending_jobs": int(status.get("pendingJobs") or 0),
        "processing_jobs": int(status.get("processingJobs") or 0),
        "retry_jobs": int(status.get("retryJobs") or 0),
        "failed_jobs": int(status.get("failedJobs") or 0),
        "oldest_pending_age_seconds": int(status.get("oldestPendingAgeSeconds") or 0),
        "recent_terminal_jobs": int(status.get("recentTerminalJobs") or 0),
        "recent_failure_rate": float(status.get("recentFailureRate") or 0),
        "average_completed_duration_seconds": float(
            status.get("averageCompletedDurationSeconds") or 0
        ),
        "healthy_processing_jobs": int(status.get("healthyProcessingJobs") or 0),
        "heartbeat_delayed_jobs": int(status.get("heartbeatDelayedJobs") or 0),
        "stalled_jobs": int(status.get("stalledJobs") or 0),
        "active_workers": active_workers,
        "known_workers": len(workers),
        "worker_status_available": bool(status.get("workerStatusAvailable", True)),
        "open_incidents": open_incidents,
        "critical_incidents": critical_incidents,
    }

    cutoff = (current - dt.timedelta(days=30)).isoformat()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"DELETE FROM operational_metric_snapshots WHERE id={ph}",
            (snapshot["id"],),
        )
        columns = tuple(snapshot.keys())
        values = [
            (
                bool(snapshot[column])
                if column == "worker_status_available" and kind == "postgres"
                else int(bool(snapshot[column]))
                if column == "worker_status_available"
                else snapshot[column]
            )
            for column in columns
        ]
        conn.execute(
            f"INSERT INTO operational_metric_snapshots({','.join(columns)}) "
            f"VALUES ({','.join([ph] * len(columns))})",
            tuple(values),
        )
        conn.execute(
            f"DELETE FROM operational_metric_snapshots WHERE sampled_at < {ph}",
            (cutoff,),
        )

    return {
        "sampledAt": sampled.isoformat(),
        "activeWorkers": active_workers,
        "openIncidents": open_incidents,
    }


def _missing_material_job_history_schema(exc: Exception) -> bool:
    """Return True only for mixed-version schemas that cannot provide job history."""
    text = str(exc or "").lower()
    columns = ("started_at", "finished_at", "status")
    if "no such table" in text and "material_jobs" in text:
        return True
    if "no such column" in text and any(column in text for column in columns):
        return True
    if "does not exist" in text and (
        "material_jobs" in text or any(column in text for column in columns)
    ):
        return True
    return False


def _terminal_jobs_since(
    cutoff: dt.datetime,
) -> tuple[list[dict[str, Any]], bool]:
    try:
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            rows = conn.execute(
                f"SELECT status,started_at,finished_at FROM material_jobs "
                f"WHERE finished_at >= {ph} AND status IN ('completed','failed') "
                f"ORDER BY finished_at ASC",
                (cutoff.isoformat(),),
            ).fetchall()
    except Exception as exc:
        if _missing_material_job_history_schema(exc):
            return [], False
        raise
    return [dict(row) for row in rows], True


def _job_period(rows: Iterable[Mapping[str, Any]], start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    selected = []
    for row in rows:
        finished = _parse_time(row.get("finished_at"))
        if not finished or not (start <= finished < end):
            continue
        selected.append((row, finished))
    completed = [pair for pair in selected if str(pair[0].get("status") or "") == "completed"]
    failed = [pair for pair in selected if str(pair[0].get("status") or "") == "failed"]
    durations = []
    for row, _finished in completed:
        started = _parse_time(row.get("started_at"))
        finished = _parse_time(row.get("finished_at"))
        if not started or not finished:
            continue
        seconds = (finished - started).total_seconds()
        if 0 <= seconds <= 7 * 24 * 3600:
            durations.append(seconds)
    terminal = len(selected)
    return {
        "terminalJobs": terminal,
        "completedJobs": len(completed),
        "failedJobs": len(failed),
        "successRate": round(len(completed) / terminal, 4) if terminal else None,
        "failureRate": round(len(failed) / terminal, 4) if terminal else None,
        "averageDurationSeconds": round(mean(durations), 1) if durations else 0.0,
        "p95DurationSeconds": round(_percentile(durations, 0.95), 1) if durations else 0.0,
        "_selected": selected,
    }



def _snapshot_rows_since(
    start: dt.datetime,
    *,
    end: dt.datetime | None = None,
) -> list[dict[str, Any]]:
    try:
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            if end is None:
                rows = conn.execute(
                    f"SELECT * FROM operational_metric_snapshots "
                    f"WHERE sampled_at >= {ph} ORDER BY sampled_at ASC",
                    (start.isoformat(),),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT * FROM operational_metric_snapshots "
                    f"WHERE sampled_at >= {ph} AND sampled_at < {ph} "
                    f"ORDER BY sampled_at ASC",
                    (start.isoformat(), end.isoformat()),
                ).fetchall()
    except Exception as exc:
        text = str(exc or "").lower()
        if "no such table" in text or ("relation" in text and "does not exist" in text):
            return []
        raise
    return [dict(row) for row in rows]


def _completed_durations(
    start: dt.datetime,
    end: dt.datetime,
) -> list[float]:
    try:
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            rows = conn.execute(
                f"SELECT started_at,finished_at FROM material_jobs "
                f"WHERE status='completed' AND finished_at >= {ph} AND finished_at < {ph} "
                f"ORDER BY finished_at ASC",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
    except Exception as exc:
        if _missing_material_job_history_schema(exc):
            return []
        raise
    values: list[float] = []
    for raw in rows:
        row = dict(raw)
        started = _parse_time(row.get("started_at"))
        finished = _parse_time(row.get("finished_at"))
        if not started or not finished:
            continue
        seconds = (finished - started).total_seconds()
        if 0 <= seconds <= 7 * 24 * 3600:
            values.append(seconds)
    return values


def _incident_open_counts(
    start: dt.datetime,
    end: dt.datetime,
) -> Counter:
    try:
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            rows = conn.execute(
                f"SELECT error_code,incident_type FROM operational_incident_events "
                f"WHERE event_type='opened' AND occurred_at >= {ph} AND occurred_at < {ph}",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
    except Exception as exc:
        text = str(exc or "").lower()
        if "no such table" in text or ("relation" in text and "does not exist" in text):
            return Counter()
        raise
    counter = Counter()
    for raw in rows:
        row = dict(raw)
        code = str(row.get("error_code") or row.get("incident_type") or "UNKNOWN").strip()
        if not code or code.startswith("TREND_") or code == "WORKER_CAPACITY_PRESSURE":
            continue
        counter[code] += 1
    return counter


def analyze_operational_trends(
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Detect sustained deterioration without promoting one-off spikes."""
    current = _utc(now)
    sample_count = _int_env("OPERATIONS_TREND_MIN_SAMPLES", 6, 6, 24)
    queue_growth_min = _int_env("OPERATIONS_TREND_QUEUE_MIN_GROWTH", 3, 2, 100)
    oldest_min = _int_env("OPERATIONS_TREND_QUEUE_OLDEST_SECONDS", 600, 120, 21600)
    duration_min_jobs = _int_env("OPERATIONS_TREND_DURATION_MIN_JOBS", 3, 2, 50)
    duration_ratio = _float_env("OPERATIONS_TREND_DURATION_RATIO", 1.5, 1.2, 5.0)
    duration_delta = _int_env("OPERATIONS_TREND_DURATION_MIN_DELTA_SECONDS", 60, 30, 7200)
    incident_min = _int_env("OPERATIONS_TREND_INCIDENT_MIN_COUNT", 3, 2, 20)
    incident_ratio = _float_env("OPERATIONS_TREND_INCIDENT_RATIO", 2.0, 1.5, 10.0)

    recent_start = current - dt.timedelta(minutes=10 * sample_count)
    snapshots = _snapshot_rows_since(recent_start)
    recent = snapshots[-sample_count:]
    signals: list[dict[str, Any]] = []
    queue_signal = None
    capacity_signal = None

    if len(recent) >= sample_count:
        pending = [int(row.get("pending_jobs") or 0) for row in recent]
        oldest = [int(row.get("oldest_pending_age_seconds") or 0) for row in recent]
        active = [
            int(row.get("active_workers") or 0)
            for row in recent
            if bool(row.get("worker_status_available"))
        ]
        half = max(1, sample_count // 2)
        first_avg = mean(pending[:half])
        second_avg = mean(pending[-half:])
        nondecreasing = sum(
            pending[index] >= pending[index - 1]
            for index in range(1, len(pending))
        )
        queue_growth = pending[-1] - pending[0]
        queue_sustained = (
            pending[-1] > 0
            and queue_growth >= queue_growth_min
            and second_avg - first_avg >= max(1.0, queue_growth_min / 2)
            and nondecreasing >= len(pending) - 2
            and max(oldest[-half:]) >= oldest_min
        )
        if queue_sustained:
            queue_signal = {
                "code": "TREND_QUEUE_GROWTH",
                "severity": "warning",
                "title": "教材 Queue 持續上升",
                "detail": (
                    f"最近 {sample_count * 10} 分鐘待處理工作由 {pending[0]} 筆升至 "
                    f"{pending[-1]} 筆，後半段平均 {round(second_avg, 1)} 筆；"
                    f"最久等待已達 {max(oldest[-half:])} 秒。"
                ),
                "action": "先確認 Worker 是否都在線，再查看處理時間與 storage/conversion Incident；不要因 queue 上升重複上傳教材。",
                "evidence": {
                    "firstPending": pending[0],
                    "lastPending": pending[-1],
                    "growth": queue_growth,
                    "oldestPendingSeconds": max(oldest[-half:]),
                    "sampleCount": sample_count,
                },
            }
            signals.append(queue_signal)

            if active:
                max_known = max(int(row.get("known_workers") or 0) for row in recent)
                recent_active = mean(active[-min(3, len(active)):])
                if max_known <= 1 and recent_active <= 1:
                    capacity_signal = {
                        "code": "WORKER_CAPACITY_PRESSURE",
                        "severity": "warning",
                        "title": "教材處理容量可能成為瓶頸",
                        "detail": (
                            f"Queue 已連續上升，而近期可用 Worker 平均僅 {round(recent_active, 1)} 台；"
                            "目前證據較符合單 Worker 容量壓力，而非單次排隊尖峰。"
                        ),
                        "action": "先排除 Worker offline、FFmpeg/LibreOffice 與 storage 異常；若依賴均正常且趨勢持續，再評估增加可用 Worker 或提升院內 Worker 處理能力。",
                        "evidence": {
                            "recentActiveWorkersAverage": round(recent_active, 2),
                            "maxKnownWorkers": max_known,
                            "queueGrowth": queue_growth,
                        },
                    }
                    signals.append(capacity_signal)
                elif max_known >= 2:
                    first_active = mean([
                        int(row.get("active_workers") or 0)
                        for row in recent[:half]
                        if bool(row.get("worker_status_available"))
                    ] or [0])
                    second_active = mean([
                        int(row.get("active_workers") or 0)
                        for row in recent[-half:]
                        if bool(row.get("worker_status_available"))
                    ] or [0])
                    if first_active - second_active >= 1:
                        capacity_signal = {
                            "code": "WORKER_CAPACITY_PRESSURE",
                            "severity": "warning",
                            "title": "可用 Worker 容量下降且 Queue 上升",
                            "detail": (
                                f"前半段平均在線 Worker {round(first_active, 1)} 台，"
                                f"後半段降至 {round(second_active, 1)} 台，同期 Queue 持續增加。"
                            ),
                            "action": "先恢復離線/不可用 Worker；若 Worker 數量恢復後 Queue 仍持續增加，再檢查單 Job 處理時間與 provider 吞吐。",
                            "evidence": {
                                "firstActiveWorkersAverage": round(first_active, 2),
                                "secondActiveWorkersAverage": round(second_active, 2),
                                "queueGrowth": queue_growth,
                            },
                        }
                        signals.append(capacity_signal)

    duration_window_hours = _int_env("OPERATIONS_TREND_DURATION_WINDOW_HOURS", 6, 1, 24)
    duration_start = current - dt.timedelta(hours=duration_window_hours)
    previous_duration_start = duration_start - dt.timedelta(hours=duration_window_hours)
    current_durations = _completed_durations(duration_start, current)
    previous_durations = _completed_durations(previous_duration_start, duration_start)
    if (
        len(current_durations) >= duration_min_jobs
        and len(previous_durations) >= duration_min_jobs
    ):
        current_p95 = _percentile(current_durations, 0.95)
        previous_p95 = _percentile(previous_durations, 0.95)
        if (
            previous_p95 > 0
            and current_p95 >= previous_p95 * duration_ratio
            and current_p95 - previous_p95 >= duration_delta
        ):
            signals.append({
                "code": "TREND_PROCESSING_SLOWDOWN",
                "severity": "warning",
                "title": "教材處理時間持續惡化",
                "detail": (
                    f"最近 {duration_window_hours} 小時 P95 約 {round(current_p95)} 秒，"
                    f"前一時段約 {round(previous_p95)} 秒，增加 "
                    f"{round((current_p95 / previous_p95 - 1) * 100)}%。"
                ),
                "action": "查看 FFmpeg/LibreOffice、storage provider 與 Worker CPU/硬體加速狀態；先找共同根因，再決定是否需要擴充 Worker 容量。",
                "evidence": {
                    "currentP95Seconds": round(current_p95, 1),
                    "previousP95Seconds": round(previous_p95, 1),
                    "currentJobs": len(current_durations),
                    "previousJobs": len(previous_durations),
                },
            })

    incident_window_hours = _int_env("OPERATIONS_TREND_INCIDENT_WINDOW_HOURS", 24, 6, 72)
    incident_start = current - dt.timedelta(hours=incident_window_hours)
    previous_incident_start = incident_start - dt.timedelta(hours=incident_window_hours)
    current_counts = _incident_open_counts(incident_start, current)
    previous_counts = _incident_open_counts(previous_incident_start, incident_start)
    for code, count in current_counts.most_common():
        previous = int(previous_counts.get(code) or 0)
        increasing = (
            count >= incident_min
            and (
                previous == 0
                or count >= max(incident_min, math.ceil(previous * incident_ratio))
            )
        )
        if not increasing:
            continue
        signals.append({
            "code": "TREND_INCIDENT_FREQUENCY",
            "severity": "warning",
            "title": f"{code} Incident 發生頻率上升",
            "detail": (
                f"最近 {incident_window_hours} 小時新開 {count} 次，"
                f"前一相同時段 {previous} 次。"
            ),
            "action": "查看該 error code 的 Runbook 與共同依賴，優先處理反覆根因，而不是逐筆重試。",
            "componentCode": code,
            "evidence": {
                "currentCount": count,
                "previousCount": previous,
                "windowHours": incident_window_hours,
            },
        })

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    signals.sort(key=lambda item: (severity_order.get(str(item.get("severity")), 9), str(item.get("code"))))
    return {
        "generatedAt": current.isoformat(),
        "sampleWindowMinutes": sample_count * 10,
        "signals": signals,
        "hasAnomaly": bool(signals),
        "capacity": (
            {
                "state": "pressure",
                "label": "可能有 Worker 容量壓力",
                "evidence": capacity_signal.get("evidence") if capacity_signal else {},
            }
            if capacity_signal
            else {
                "state": "watch" if queue_signal else "normal",
                "label": "持續觀察 Queue" if queue_signal else "目前沒有持續容量壓力訊號",
                "evidence": queue_signal.get("evidence") if queue_signal else {},
            }
        ),
    }


def trend_incident_candidates(
    *,
    now: dt.datetime | None = None,
) -> list[dict[str, Any]]:
    """Convert sustained trend signals into de-duplicated operational incidents."""
    analysis = analyze_operational_trends(now=now)
    candidates: list[dict[str, Any]] = []
    for signal in analysis.get("signals") or []:
        code = str(signal.get("code") or "")
        component = str(signal.get("componentCode") or "")
        suffix = component.lower() if code == "TREND_INCIDENT_FREQUENCY" and component else code.lower()
        candidates.append({
            "incidentKey": f"trend:{suffix}",
            "incidentType": "trend_anomaly",
            "category": "capacity" if code == "WORKER_CAPACITY_PRESSURE" else "trend",
            "severity": str(signal.get("severity") or "warning"),
            "title": str(signal.get("title") or "維運趨勢異常"),
            "detail": str(signal.get("detail") or ""),
            "action": str(signal.get("action") or ""),
            "errorCode": code,
            "resourceId": component or code,
        })
    return candidates


def build_operational_dashboard(
    *,
    window: str = "24h",
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build one truthful 24h/7d SLO view from real jobs and sampled history."""
    current = _utc(now)
    hours = _window_hours(window)
    start = current - dt.timedelta(hours=hours)
    previous_start = start - dt.timedelta(hours=hours)

    terminal_rows, material_job_history_available = _terminal_jobs_since(previous_start)
    current_jobs = _job_period(terminal_rows, start, current)
    previous_jobs = _job_period(terminal_rows, previous_start, start)

    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        try:
            snapshot_rows = conn.execute(
                f"SELECT * FROM operational_metric_snapshots "
                f"WHERE sampled_at >= {ph} AND sampled_at <= {ph} "
                f"ORDER BY sampled_at ASC",
                (start.isoformat(), current.isoformat()),
            ).fetchall()
            incident_rows = conn.execute(
                f"SELECT * FROM operational_incident_events "
                f"WHERE occurred_at >= {ph} AND occurred_at <= {ph} "
                f"ORDER BY occurred_at ASC",
                (start.isoformat(), current.isoformat()),
            ).fetchall()
            first_sample = conn.execute(
                "SELECT MIN(sampled_at) AS first_sample FROM operational_metric_snapshots"
            ).fetchone()
            current_open = conn.execute(
                "SELECT COUNT(*) AS count FROM operational_incidents WHERE status='open'"
            ).fetchone()
        except Exception:
            snapshot_rows = []
            incident_rows = []
            first_sample = None
            current_open = None

    snapshots = [dict(row) for row in snapshot_rows]
    incident_events = [dict(row) for row in incident_rows]
    available_samples = [
        row for row in snapshots if bool(row.get("worker_status_available"))
    ]
    worker_up_samples = [
        row for row in available_samples if int(row.get("active_workers") or 0) > 0
    ]
    availability = (
        round(len(worker_up_samples) / len(available_samples), 4)
        if available_samples
        else None
    )

    resolved_events = [
        row for row in incident_events
        if str(row.get("event_type") or "") == "resolved"
        and int(row.get("duration_seconds") or 0) >= 0
    ]
    mttr_values = [int(row.get("duration_seconds") or 0) for row in resolved_events]
    opened_events = [
        row for row in incident_events
        if str(row.get("event_type") or "") == "opened"
    ]
    top_codes = Counter(
        str(row.get("error_code") or row.get("incident_type") or "UNKNOWN")
        for row in opened_events
    )

    bucketed: dict[str, dict[str, Any]] = {}
    for row in snapshots:
        sampled = _parse_time(row.get("sampled_at"))
        if not sampled:
            continue
        bucket = _bucket_start(sampled, hours=hours).isoformat()
        entry = bucketed.setdefault(bucket, {
            "sampledAt": bucket,
            "pending": [],
            "activeWorkers": [],
            "failureRates": [],
            "durations": [],
            "openIncidents": [],
        })
        entry["pending"].append(int(row.get("pending_jobs") or 0))
        entry["activeWorkers"].append(int(row.get("active_workers") or 0))
        entry["failureRates"].append(float(row.get("recent_failure_rate") or 0))
        entry["durations"].append(float(row.get("average_completed_duration_seconds") or 0))
        entry["openIncidents"].append(int(row.get("open_incidents") or 0))

    job_buckets: dict[str, dict[str, int]] = {}
    for row, finished in current_jobs["_selected"]:
        bucket = _bucket_start(finished, hours=hours).isoformat()
        entry = job_buckets.setdefault(bucket, {"completedJobs": 0, "failedJobs": 0})
        key = "completedJobs" if str(row.get("status") or "") == "completed" else "failedJobs"
        entry[key] += 1

    series = []
    for key in sorted(set(bucketed) | set(job_buckets)):
        entry = bucketed.get(key, {})
        jobs = job_buckets.get(key, {"completedJobs": 0, "failedJobs": 0})
        series.append({
            "sampledAt": key,
            "pendingJobsAverage": round(mean(entry.get("pending") or [0]), 2),
            "pendingJobsMax": max(entry.get("pending") or [0]),
            "activeWorkersAverage": round(mean(entry.get("activeWorkers") or [0]), 2),
            "recentFailureRateAverage": round(mean(entry.get("failureRates") or [0]), 4),
            "completedDurationAverageSeconds": round(mean(entry.get("durations") or [0]), 1),
            "openIncidentsAverage": round(mean(entry.get("openIncidents") or [0]), 2),
            **jobs,
        })

    current_avg = float(current_jobs["averageDurationSeconds"] or 0)
    previous_avg = float(previous_jobs["averageDurationSeconds"] or 0)
    duration_change = (
        round((current_avg - previous_avg) / previous_avg * 100, 1)
        if current_avg > 0 and previous_avg > 0
        else None
    )

    first_sample_value = ""
    if first_sample:
        first_sample_value = str(dict(first_sample).get("first_sample") or "")

    targets = {
        "workerAvailabilityPercent": _optional_float(
            "OPERATIONS_SLO_WORKER_AVAILABILITY_PERCENT"
        ),
        "materialSuccessPercent": _optional_float(
            "MATERIAL_SLO_SUCCESS_PERCENT"
        ),
        "materialP95DurationSeconds": _optional_float(
            "MATERIAL_SLO_P95_DURATION_SECONDS"
        ),
    }

    current_jobs.pop("_selected", None)
    previous_jobs.pop("_selected", None)
    return {
        "window": "7d" if hours == 168 else "24h",
        "windowHours": hours,
        "generatedAt": current.isoformat(),
        "dataCoverage": {
            "sampledHistoryAvailable": bool(snapshots),
            "materialJobHistoryAvailable": material_job_history_available,
            "firstSampleAt": first_sample_value,
            "windowSampleCount": len(snapshots),
            "expectedSampleCount": hours * 6,
            "coveragePercent": round(
                min(1.0, len(snapshots) / max(1, hours * 6)), 4
            ),
            "note": (
                "queue / Worker availability 自 0110 上線後每 10 分鐘採樣；"
                + (
                    "教材成功率與處理時間可由既有 material_jobs 回算。"
                    if material_job_history_available
                    else "目前 schema 尚無可回算的 material_jobs 完成時間欄位。"
                )
            ),
        },
        "material": {
            **current_jobs,
            "previousAverageDurationSeconds": previous_avg,
            "durationChangePercent": duration_change,
        },
        "queue": {
            "averagePendingJobs": round(
                mean([int(row.get("pending_jobs") or 0) for row in snapshots]), 2
            ) if snapshots else None,
            "maxPendingJobs": max(
                [int(row.get("pending_jobs") or 0) for row in snapshots],
                default=0,
            ),
            "maxOldestPendingAgeSeconds": max(
                [int(row.get("oldest_pending_age_seconds") or 0) for row in snapshots],
                default=0,
            ),
            "maxStalledJobs": max(
                [int(row.get("stalled_jobs") or 0) for row in snapshots],
                default=0,
            ),
        },
        "worker": {
            "observedAvailability": availability,
            "availableSamples": len(available_samples),
            "unknownSamples": len(snapshots) - len(available_samples),
            "maxKnownWorkers": max(
                [int(row.get("known_workers") or 0) for row in snapshots],
                default=0,
            ),
        },
        "incidents": {
            "opened": len(opened_events),
            "resolved": len(resolved_events),
            "currentlyOpen": int(dict(current_open).get("count") or 0)
            if current_open
            else 0,
            "averageMttrSeconds": round(mean(mttr_values), 1)
            if mttr_values
            else 0.0,
            "p95MttrSeconds": round(_percentile(mttr_values, 0.95), 1)
            if mttr_values
            else 0.0,
            "topComponents": [
                {"code": code, "count": count}
                for code, count in top_codes.most_common(5)
            ],
        },
        "targets": targets,
        "targetsConfigured": any(value is not None for value in targets.values()),
        "trendAnalysis": analyze_operational_trends(now=current),
        "series": series,
    }


__all__ = [
    "analyze_operational_trends",
    "build_operational_dashboard",
    "record_operational_sample",
    "trend_incident_candidates",
]
