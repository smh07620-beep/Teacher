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
        "series": series,
    }


__all__ = ["build_operational_dashboard", "record_operational_sample"]
