"""Historical operational samples and truthful SLO/trend projections."""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
import os
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping

from teacher_app.common import db as common_db
from teacher_app.materials.validation import IMAGE_EXT, MEDIA_EXT, PDF_EXT, TEXT_EXT
from teacher_app.worker import operations as worker_operations


LOGGER = logging.getLogger(__name__)


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

    prediction_calibration = {}
    try:
        prediction_calibration = reconcile_forecast_predictions(now=current)
    except Exception as exc:
        LOGGER.warning(
            "forecast prediction calibration failed error_type=%s",
            type(exc).__name__,
        )

    return {
        "sampledAt": sampled.isoformat(),
        "activeWorkers": active_workers,
        "openIncidents": open_incidents,
        "predictionCalibration": prediction_calibration,
    }


def _missing_material_job_history_schema(exc: Exception) -> bool:
    """Return True only for mixed-version schemas that cannot provide job history."""
    text = str(exc or "").lower()
    columns = (
        "started_at",
        "finished_at",
        "created_at",
        "status",
        "original_name",
        "source_bytes",
        "result",
    )
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



def _job_arrival_count(
    start: dt.datetime,
    end: dt.datetime,
) -> tuple[int, bool]:
    try:
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            row = conn.execute(
                f"SELECT COUNT(*) AS count FROM material_jobs "
                f"WHERE created_at >= {ph} AND created_at < {ph}",
                (start.isoformat(), end.isoformat()),
            ).fetchone()
    except Exception as exc:
        if _missing_material_job_history_schema(exc):
            return 0, False
        text = str(exc or "").lower()
        if "created_at" in text and (
            "no such column" in text or "does not exist" in text
        ):
            return 0, False
        raise
    return int(dict(row).get("count") or 0) if row else 0, True



_DOCUMENT_EXT = {
    ".pptx", ".ppt", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".odp", ".odt", ".ods", ".txt", ".csv", ".srt", ".vtt",
}
_WORKLOAD_LABELS = {
    "document": "文件 / PDF / Office",
    "media": "影音",
    "image": "圖片",
    "archive": "ZIP / 封裝",
    "other": "其他",
}


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not value:
        return {}
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(decoded) if isinstance(decoded, Mapping) else {}


def _workload_kind(original_name: Any, result: Any = None) -> str:
    payload = _json_mapping(result)
    meta = _json_mapping(payload.get("storageMeta"))
    media_kind = str(meta.get("mediaKind") or "").strip().lower()
    if media_kind in {"video", "audio"}:
        return "media"
    ext = Path(str(original_name or "")).suffix.lower()
    if ext in MEDIA_EXT:
        return "media"
    if ext in IMAGE_EXT:
        return "image"
    if ext == ".zip":
        return "archive"
    if ext in _DOCUMENT_EXT or ext in PDF_EXT or ext in TEXT_EXT:
        return "document"
    return "other"


def _size_band(source_bytes: Any) -> str:
    try:
        value = max(0, int(source_bytes or 0))
    except (TypeError, ValueError):
        value = 0
    if value < 10 * 1024 * 1024:
        return "small"
    if value < 100 * 1024 * 1024:
        return "medium"
    return "large"


def _workload_rows(
    *,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
    completed_only: bool = False,
    backlog_only: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    clauses = []
    values: list[Any] = []
    try:
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            if completed_only:
                clauses.append("status='completed'")
                if start is not None:
                    clauses.append(f"finished_at >= {ph}")
                    values.append(start.isoformat())
                if end is not None:
                    clauses.append(f"finished_at < {ph}")
                    values.append(end.isoformat())
            elif backlog_only:
                clauses.append("status IN ('queued','retry_wait','processing')")
            else:
                if start is not None:
                    clauses.append(f"created_at >= {ph}")
                    values.append(start.isoformat())
                if end is not None:
                    clauses.append(f"created_at < {ph}")
                    values.append(end.isoformat())
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            rows = conn.execute(
                "SELECT id,status,created_at,started_at,finished_at,"
                "original_name,source_bytes,result FROM material_jobs"
                + where,
                tuple(values),
            ).fetchall()
    except Exception as exc:
        if _missing_material_job_history_schema(exc):
            return [], False
        text = str(exc or "").lower()
        if (
            "original_name" in text
            or "source_bytes" in text
            or "result" in text
        ) and ("no such column" in text or "does not exist" in text):
            return [], False
        raise
    return [dict(row) for row in rows], True


def _completed_workload_metrics(row: Mapping[str, Any]) -> dict[str, Any] | None:
    started = _parse_time(row.get("started_at"))
    finished = _parse_time(row.get("finished_at"))
    if not started or not finished:
        return None
    processing_seconds = (finished - started).total_seconds()
    if processing_seconds < 0 or processing_seconds > 7 * 24 * 3600:
        return None
    result = _json_mapping(row.get("result"))
    meta = _json_mapping(result.get("storageMeta"))
    try:
        pages = max(0, int(result.get("pageCount") or 0))
    except (TypeError, ValueError):
        pages = 0
    try:
        media_seconds = max(0.0, float(meta.get("durationSeconds") or 0))
    except (TypeError, ValueError):
        media_seconds = 0.0
    try:
        source_bytes = max(0, int(row.get("source_bytes") or 0))
    except (TypeError, ValueError):
        source_bytes = 0
    return {
        "kind": _workload_kind(row.get("original_name"), result),
        "processingSeconds": float(processing_seconds),
        "sourceBytes": source_bytes,
        "sizeBand": _size_band(source_bytes),
        "pageCount": pages,
        "mediaDurationSeconds": media_seconds,
        "transcodeMode": str(meta.get("transcodeMode") or ""),
    }


def build_workload_calibration(
    *,
    now: dt.datetime | None = None,
    window_hours: int | None = None,
    current_active_workers: int | None = None,
) -> dict[str, Any]:
    """Calibrate service time by material workload instead of equal-job weighting."""
    current = _utc(now)
    hours = int(
        window_hours
        if window_hours is not None
        else _int_env("OPERATIONS_FORECAST_WINDOW_HOURS", 6, 2, 24)
    )
    hours = max(2, min(24, hours))
    min_per_kind = _int_env(
        "OPERATIONS_FORECAST_MIN_WORKLOAD_COMPLETED_JOBS",
        2,
        2,
        20,
    )
    start = current - dt.timedelta(hours=hours)
    completed_rows, completed_available = _workload_rows(
        start=start,
        end=current,
        completed_only=True,
    )
    arrival_rows, arrivals_available = _workload_rows(
        start=start,
        end=current,
    )
    backlog_rows, backlog_available = _workload_rows(backlog_only=True)
    if not (completed_available and arrivals_available and backlog_available):
        return {
            "available": False,
            "fullyCalibrated": False,
            "windowHours": hours,
            "profiles": [],
            "limitations": ["目前 schema 尚無完整 workload metadata，保留全體 Job Forecast。"],
        }

    completed_by_kind: dict[str, list[dict[str, Any]]] = {}
    for row in completed_rows:
        metric = _completed_workload_metrics(row)
        if not metric:
            continue
        completed_by_kind.setdefault(metric["kind"], []).append(metric)

    arrivals = Counter(
        _workload_kind(row.get("original_name"), row.get("result"))
        for row in arrival_rows
    )
    backlog = Counter(
        _workload_kind(row.get("original_name"), row.get("result"))
        for row in backlog_rows
    )
    backlog_bytes = Counter()
    for row in backlog_rows:
        kind = _workload_kind(row.get("original_name"), row.get("result"))
        try:
            backlog_bytes[kind] += max(0, int(row.get("source_bytes") or 0))
        except (TypeError, ValueError):
            pass

    profiles = []
    workload_nominal_demand = 0.0
    workload_conservative_demand = 0.0
    backlog_nominal_hours = 0.0
    backlog_conservative_hours = 0.0
    uncalibrated_arrivals = 0
    uncalibrated_backlog = 0

    kinds = sorted(
        set(completed_by_kind) | set(arrivals) | set(backlog),
        key=lambda kind: (
            {"media": 0, "document": 1, "image": 2, "archive": 3, "other": 4}.get(kind, 9),
            kind,
        ),
    )
    for kind in kinds:
        samples = completed_by_kind.get(kind, [])
        durations = [row["processingSeconds"] for row in samples]
        source_sizes = [row["sourceBytes"] for row in samples if row["sourceBytes"] > 0]
        nominal = _percentile(durations, 0.5) if durations else 0.0
        conservative = _percentile(durations, 0.95) if durations else 0.0
        calibrated = len(durations) >= min_per_kind and nominal > 0 and conservative > 0
        arrival_count = int(arrivals.get(kind) or 0)
        arrival_rate = arrival_count / hours
        backlog_count = int(backlog.get(kind) or 0)

        if calibrated:
            workload_nominal_demand += arrival_rate * nominal / 3600
            workload_conservative_demand += arrival_rate * conservative / 3600
            backlog_nominal_hours += backlog_count * nominal / 3600
            backlog_conservative_hours += backlog_count * conservative / 3600
        else:
            uncalibrated_arrivals += arrival_count
            uncalibrated_backlog += backlog_count

        page_rows = [row for row in samples if row["pageCount"] > 0]
        media_rows = [row for row in samples if row["mediaDurationSeconds"] > 0]
        seconds_per_page = [
            row["processingSeconds"] / row["pageCount"]
            for row in page_rows
            if row["pageCount"] > 0
        ]
        realtime_factors = [
            row["processingSeconds"] / row["mediaDurationSeconds"]
            for row in media_rows
            if row["mediaDurationSeconds"] > 0
        ]
        size_bands = []
        for band in ("small", "medium", "large"):
            band_durations = [
                row["processingSeconds"]
                for row in samples
                if row["sizeBand"] == band
            ]
            if not band_durations:
                continue
            size_bands.append({
                "band": band,
                "samples": len(band_durations),
                "medianDurationSeconds": round(
                    _percentile(band_durations, 0.5), 1
                ),
                "p95DurationSeconds": round(
                    _percentile(band_durations, 0.95), 1
                ),
            })

        profiles.append({
            "kind": kind,
            "label": _WORKLOAD_LABELS.get(kind, kind),
            "calibrated": calibrated,
            "completedSamples": len(durations),
            "arrivalJobs": arrival_count,
            "arrivalPerHour": round(arrival_rate, 2),
            "backlogJobs": backlog_count,
            "backlogBytes": int(backlog_bytes.get(kind) or 0),
            "medianDurationSeconds": round(nominal, 1) if nominal else 0.0,
            "p95DurationSeconds": round(conservative, 1) if conservative else 0.0,
            "medianSourceBytes": round(_percentile(source_sizes, 0.5))
            if source_sizes
            else 0,
            "pageMetadataCoverage": round(
                len(page_rows) / len(samples), 4
            ) if samples else 0.0,
            "medianPageCount": round(
                _percentile([row["pageCount"] for row in page_rows], 0.5), 1
            ) if page_rows else 0.0,
            "medianSecondsPerPage": round(
                _percentile(seconds_per_page, 0.5), 2
            ) if seconds_per_page else 0.0,
            "p95SecondsPerPage": round(
                _percentile(seconds_per_page, 0.95), 2
            ) if seconds_per_page else 0.0,
            "mediaMetadataCoverage": round(
                len(media_rows) / len(samples), 4
            ) if samples else 0.0,
            "medianMediaDurationSeconds": round(
                _percentile(
                    [row["mediaDurationSeconds"] for row in media_rows],
                    0.5,
                ),
                1,
            ) if media_rows else 0.0,
            "medianProcessingToMediaRatio": round(
                _percentile(realtime_factors, 0.5), 3
            ) if realtime_factors else 0.0,
            "p95ProcessingToMediaRatio": round(
                _percentile(realtime_factors, 0.95), 3
            ) if realtime_factors else 0.0,
            "sizeBands": size_bands,
        })

    active_workers = max(0, int(current_active_workers or 0))
    fully_calibrated = (
        bool(profiles)
        and uncalibrated_arrivals == 0
        and uncalibrated_backlog == 0
        and any(profile["calibrated"] for profile in profiles)
    )

    def mixed_scenario(workers: int, conservative: bool) -> dict[str, Any]:
        if not fully_calibrated or workers <= 0:
            return {
                "workers": workers,
                "state": "unavailable",
                "utilization": None,
                "netWorkerHoursPerHour": None,
                "backlogServiceHours": None,
                "clearEtaSeconds": None,
            }
        demand = (
            workload_conservative_demand
            if conservative
            else workload_nominal_demand
        )
        backlog_hours = (
            backlog_conservative_hours
            if conservative
            else backlog_nominal_hours
        )
        net = workers - demand
        eta = (
            backlog_hours / net * 3600
            if backlog_hours > 0 and net > 0
            else 0
            if backlog_hours == 0
            else None
        )
        return {
            "workers": workers,
            "state": "clearing" if net > 0 else "growing",
            "utilization": round(demand / workers, 4) if workers else None,
            "netWorkerHoursPerHour": round(net, 3),
            "backlogServiceHours": round(backlog_hours, 3),
            "clearEtaSeconds": round(eta) if eta is not None else None,
        }

    limitations = []
    if uncalibrated_arrivals:
        limitations.append(
            f"最近到達工作仍有 {uncalibrated_arrivals} 筆屬於樣本不足的 workload 類型。"
        )
    if uncalibrated_backlog:
        limitations.append(
            f"目前 backlog 仍有 {uncalibrated_backlog} 筆 workload 尚未完成校準。"
        )
    if not profiles:
        limitations.append("目前沒有可用的 workload 完成樣本。")

    return {
        "available": bool(profiles),
        "fullyCalibrated": fully_calibrated,
        "windowHours": hours,
        "minimumCompletedPerKind": min_per_kind,
        "profiles": profiles,
        "uncalibratedArrivalJobs": uncalibrated_arrivals,
        "uncalibratedBacklogJobs": uncalibrated_backlog,
        "nominalWorkerDemand": round(workload_nominal_demand, 3),
        "conservativeWorkerDemand": round(workload_conservative_demand, 3),
        "nominalBacklogServiceHours": round(backlog_nominal_hours, 3),
        "conservativeBacklogServiceHours": round(backlog_conservative_hours, 3),
        "current": {
            "nominal": mixed_scenario(active_workers, False),
            "conservative": mixed_scenario(active_workers, True),
        },
        "plusOneWorker": {
            "nominal": mixed_scenario(active_workers + 1, False),
            "conservative": mixed_scenario(active_workers + 1, True),
        },
        "limitations": limitations,
    }



def _bounded_scenario_int(
    scenario: Mapping[str, Any],
    key: str,
    *,
    default: int = 0,
    minimum: int = 0,
    maximum: int = 100,
) -> int:
    try:
        value = int(scenario.get(key, default) or 0)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _bounded_scenario_float(
    scenario: Mapping[str, Any],
    key: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(scenario.get(key, default) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def simulate_capacity_what_if(
    scenario: Mapping[str, Any],
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Simulate a one-time peak batch against current workload-calibrated demand."""
    current = _utc(now)
    forecast = build_capacity_forecast(now=current)
    workload = dict(forecast.get("workloadCalibration") or {})
    profiles = {
        str(profile.get("kind") or ""): dict(profile)
        for profile in workload.get("profiles") or []
    }

    document_count = _bounded_scenario_int(
        scenario, "documentCount", maximum=100
    )
    document_pages = _bounded_scenario_float(
        scenario,
        "documentPages",
        default=20,
        minimum=1,
        maximum=500,
    )
    media_count = _bounded_scenario_int(
        scenario, "mediaCount", maximum=50
    )
    media_minutes = _bounded_scenario_float(
        scenario,
        "mediaMinutes",
        default=30,
        minimum=1,
        maximum=240,
    )
    image_count = _bounded_scenario_int(
        scenario, "imageCount", maximum=100
    )
    archive_count = _bounded_scenario_int(
        scenario, "archiveCount", maximum=50
    )

    requested = [
        ("document", document_count),
        ("media", media_count),
        ("image", image_count),
        ("archive", archive_count),
    ]
    total_jobs = sum(count for _kind, count in requested)
    limitations: list[str] = []
    components: list[dict[str, Any]] = []
    scenario_nominal_hours = 0.0
    scenario_conservative_hours = 0.0

    for kind, count in requested:
        if count <= 0:
            continue
        profile = profiles.get(kind) or {}
        if not profile.get("calibrated"):
            limitations.append(
                f"{_WORKLOAD_LABELS.get(kind, kind)} 尚未有足夠完成樣本，"
                "不能安全估算這批高峰工作。"
            )
            components.append({
                "kind": kind,
                "label": _WORKLOAD_LABELS.get(kind, kind),
                "count": count,
                "calibrated": False,
                "nominalServiceSecondsEach": None,
                "conservativeServiceSecondsEach": None,
                "method": "unavailable",
            })
            continue

        nominal_each = float(profile.get("medianDurationSeconds") or 0)
        conservative_each = float(profile.get("p95DurationSeconds") or 0)
        method = "class_duration"

        if kind == "document":
            nominal_per_page = float(profile.get("medianSecondsPerPage") or 0)
            conservative_per_page = float(profile.get("p95SecondsPerPage") or 0)
            if nominal_per_page > 0 and conservative_per_page > 0:
                nominal_each = document_pages * nominal_per_page
                conservative_each = document_pages * conservative_per_page
                method = "pages"
        elif kind == "media":
            nominal_ratio = float(
                profile.get("medianProcessingToMediaRatio") or 0
            )
            conservative_ratio = float(
                profile.get("p95ProcessingToMediaRatio") or 0
            )
            if nominal_ratio > 0 and conservative_ratio > 0:
                media_seconds = media_minutes * 60
                nominal_each = media_seconds * nominal_ratio
                conservative_each = media_seconds * conservative_ratio
                method = "media_duration"

        if nominal_each <= 0 or conservative_each <= 0:
            limitations.append(
                f"{_WORKLOAD_LABELS.get(kind, kind)} 校準資料不完整，"
                "無法取得 nominal / P95 service time。"
            )
            components.append({
                "kind": kind,
                "label": _WORKLOAD_LABELS.get(kind, kind),
                "count": count,
                "calibrated": False,
                "nominalServiceSecondsEach": None,
                "conservativeServiceSecondsEach": None,
                "method": "unavailable",
            })
            continue

        nominal_hours = count * nominal_each / 3600
        conservative_hours = count * conservative_each / 3600
        scenario_nominal_hours += nominal_hours
        scenario_conservative_hours += conservative_hours
        components.append({
            "kind": kind,
            "label": _WORKLOAD_LABELS.get(kind, kind),
            "count": count,
            "calibrated": True,
            "method": method,
            "inputPagesEach": document_pages if kind == "document" else None,
            "inputMediaMinutesEach": media_minutes if kind == "media" else None,
            "nominalServiceSecondsEach": round(nominal_each, 1),
            "conservativeServiceSecondsEach": round(conservative_each, 1),
            "nominalWorkerHours": round(nominal_hours, 3),
            "conservativeWorkerHours": round(conservative_hours, 3),
        })

    fully_estimable = (
        total_jobs > 0
        and bool(workload.get("fullyCalibrated"))
        and not limitations
        and all(component.get("calibrated") for component in components)
    )
    if total_jobs <= 0:
        limitations.append("請至少輸入一種高峰 workload。")
    if not workload.get("fullyCalibrated"):
        limitations.append(
            "目前到達流量或既有 backlog 仍含未校準 workload，"
            "因此不能把 What-if 與目前 Queue 合併成可信 ETA。"
        )

    baseline_nominal = float(workload.get("nominalWorkerDemand") or 0)
    baseline_conservative = float(
        workload.get("conservativeWorkerDemand") or 0
    )
    backlog_nominal = float(
        workload.get("nominalBacklogServiceHours") or 0
    )
    backlog_conservative = float(
        workload.get("conservativeBacklogServiceHours") or 0
    )
    current_backlog_jobs = int(
        (forecast.get("queue") or {}).get("backlogJobs") or 0
    )
    peak_backlog_jobs = current_backlog_jobs + total_jobs

    def worker_scenario(workers: int, conservative: bool) -> dict[str, Any]:
        if not fully_estimable:
            return {
                "workers": workers,
                "state": "unavailable",
                "baselineUtilization": None,
                "netWorkerHoursPerHour": None,
                "peakBacklogJobs": peak_backlog_jobs,
                "peakServiceHours": None,
                "clearEtaSeconds": None,
            }
        demand = baseline_conservative if conservative else baseline_nominal
        existing = backlog_conservative if conservative else backlog_nominal
        injected = (
            scenario_conservative_hours
            if conservative
            else scenario_nominal_hours
        )
        service_hours = existing + injected
        net = workers - demand
        eta = (
            service_hours / net * 3600
            if service_hours > 0 and net > 0
            else 0
            if service_hours == 0
            else None
        )
        return {
            "workers": workers,
            "state": "clearing" if net > 0 else "growing",
            "baselineUtilization": round(demand / workers, 4)
            if workers
            else None,
            "netWorkerHoursPerHour": round(net, 3),
            "peakBacklogJobs": peak_backlog_jobs,
            "peakServiceHours": round(service_hours, 3),
            "clearEtaSeconds": round(eta) if eta is not None else None,
        }

    one_nominal = worker_scenario(1, False)
    one_conservative = worker_scenario(1, True)
    two_nominal = worker_scenario(2, False)
    two_conservative = worker_scenario(2, True)

    bottleneck = None
    calibrated_components = [
        component
        for component in components
        if component.get("calibrated")
    ]
    if calibrated_components:
        biggest = max(
            calibrated_components,
            key=lambda item: float(item.get("conservativeWorkerHours") or 0),
        )
        total_conservative = sum(
            float(item.get("conservativeWorkerHours") or 0)
            for item in calibrated_components
        )
        bottleneck = {
            "kind": biggest.get("kind"),
            "label": biggest.get("label"),
            "conservativeWorkerHours": biggest.get(
                "conservativeWorkerHours"
            ),
            "share": round(
                float(biggest.get("conservativeWorkerHours") or 0)
                / total_conservative,
                4,
            )
            if total_conservative > 0
            else 0.0,
        }

    decision = {
        "state": "insufficient_data",
        "label": "目前無法安全估算這個高峰情境",
        "detail": "先累積缺少的 workload 完成樣本，再進行 Worker 數量比較。",
    }
    blockers = list(forecast.get("blockers") or [])
    if fully_estimable and blockers:
        decision = {
            "state": "dependency_blocked",
            "label": "可試算，但先排除目前故障",
            "detail": (
                "What-if 數學可以計算，但目前有 Worker/provider/conversion "
                "Incident，實際速度可能偏離校準值。"
            ),
        }
    elif fully_estimable and one_conservative["state"] == "clearing":
        decision = {
            "state": "one_worker_sufficient",
            "label": "1 台 Worker 在 P95 保守情境仍可清空",
            "detail": (
                "在目前背景到達率持續存在的前提下，1 台 Worker 的保守容量"
                "仍高於負載；第 2 台主要縮短高峰等待時間。"
            ),
        }
    elif (
        fully_estimable
        and one_nominal["state"] == "clearing"
        and one_conservative["state"] == "growing"
        and two_conservative["state"] == "clearing"
    ):
        decision = {
            "state": "two_workers_for_resilience",
            "label": "1 台接近臨界，2 台可承受 P95 高峰",
            "detail": (
                "1 台在 nominal 情境可清 Queue，但 P95 保守情境會持續堆積；"
                "2 台可恢復保守淨消化能力。"
            ),
        }
    elif (
        fully_estimable
        and one_nominal["state"] == "growing"
        and two_conservative["state"] == "clearing"
    ):
        decision = {
            "state": "two_workers_recommended_for_peak",
            "label": "這個高峰情境需要 2 台才有保守淨消化能力",
            "detail": (
                "1 台連 nominal 容量都低於背景到達率；2 台在 P95 情境"
                "仍可逐步清空 Queue。"
            ),
        }
    elif fully_estimable and two_nominal["state"] == "clearing":
        decision = {
            "state": "two_workers_may_help",
            "label": "2 台可改善，但 P95 仍有壓力",
            "detail": (
                "2 台 Worker 在 nominal 情境可清空，但 P95 保守情境仍可能"
                "持續堆積；應先降低主要 bottleneck workload 的單 Job 成本。"
            ),
        }
    elif fully_estimable:
        decision = {
            "state": "more_than_two_or_optimize",
            "label": "2 台 Worker 仍不足以穩定承受此高峰",
            "detail": (
                "在目前背景到達率與 workload service time 下，單純增加到 2 台"
                "仍不足；需降低瓶頸處理時間或重新規劃高峰上傳節奏。"
            ),
        }

    return {
        "generatedAt": current.isoformat(),
        "scenario": {
            "documentCount": document_count,
            "documentPages": document_pages,
            "mediaCount": media_count,
            "mediaMinutes": media_minutes,
            "imageCount": image_count,
            "archiveCount": archive_count,
            "totalJobs": total_jobs,
        },
        "available": fully_estimable,
        "windowHours": int(workload.get("windowHours") or 0),
        "components": components,
        "scenarioNominalWorkerHours": round(
            scenario_nominal_hours, 3
        ),
        "scenarioConservativeWorkerHours": round(
            scenario_conservative_hours, 3
        ),
        "currentBacklogJobs": current_backlog_jobs,
        "peakBacklogJobs": peak_backlog_jobs,
        "baseline": {
            "nominalWorkerDemand": round(baseline_nominal, 3),
            "conservativeWorkerDemand": round(
                baseline_conservative, 3
            ),
        },
        "oneWorker": {
            "nominal": one_nominal,
            "conservative": one_conservative,
        },
        "twoWorkers": {
            "nominal": two_nominal,
            "conservative": two_conservative,
        },
        "bottleneck": bottleneck,
        "blockers": blockers,
        "limitations": list(dict.fromkeys(limitations)),
        "decision": decision,
    }



def _prediction_table_unavailable(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return (
        ("no such table" in text and "operational_forecast_predictions" in text)
        or (
            "relation" in text
            and "operational_forecast_predictions" in text
            and "does not exist" in text
        )
    )


def reconcile_forecast_predictions(
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Create pre-completion service-time predictions and score terminal jobs."""
    current = _utc(now)
    evaluated = 0
    ignored = 0
    created = 0

    try:
        with common_db.read_connection() as (conn, _kind):
            rows = conn.execute(
                """SELECT p.*,j.status AS job_status,j.started_at AS job_started_at,
                          j.finished_at AS job_finished_at
                   FROM operational_forecast_predictions p
                   LEFT JOIN material_jobs j ON j.id=p.job_id
                   WHERE p.evaluation_status='pending'"""
            ).fetchall()
    except Exception as exc:
        if _prediction_table_unavailable(exc) or _missing_material_job_history_schema(exc):
            return {
                "available": False,
                "created": 0,
                "evaluated": 0,
                "ignored": 0,
            }
        raise

    pending_rows = [dict(row) for row in rows]
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        for row in pending_rows:
            status = str(row.get("job_status") or "")
            predicted_at = _parse_time(row.get("predicted_at"))
            if status == "completed":
                started = _parse_time(row.get("job_started_at"))
                finished = _parse_time(row.get("job_finished_at"))
                if not started or not finished:
                    continue
                actual = (finished - started).total_seconds()
                if actual <= 0 or actual > 7 * 24 * 3600:
                    continue
                predicted = max(
                    0.0, float(row.get("predicted_nominal_seconds") or 0)
                )
                predicted_p95 = max(
                    0.0, float(row.get("predicted_p95_seconds") or 0)
                )
                absolute_error = abs(predicted - actual)
                ape = absolute_error / actual if actual > 0 else 0.0
                signed = (predicted - actual) / actual if actual > 0 else 0.0
                p95_covered = predicted_p95 >= actual
                covered_value = (
                    bool(p95_covered)
                    if kind == "postgres"
                    else int(bool(p95_covered))
                )
                conn.execute(
                    f"""UPDATE operational_forecast_predictions SET
                        evaluation_status={ph},completed_at={ph},actual_seconds={ph},
                        nominal_absolute_error_seconds={ph},
                        nominal_absolute_percentage_error={ph},
                        nominal_signed_percentage_error={ph},
                        p95_covered={ph},evaluated_at={ph}
                        WHERE id={ph}""",
                    (
                        "evaluated",
                        finished.isoformat(),
                        round(actual, 3),
                        round(absolute_error, 3),
                        round(ape, 6),
                        round(signed, 6),
                        covered_value,
                        current.isoformat(),
                        row.get("id"),
                    ),
                )
                evaluated += 1
            elif status in {"failed", "cancelled"}:
                conn.execute(
                    f"""UPDATE operational_forecast_predictions SET
                        evaluation_status={ph},completed_at={ph},evaluated_at={ph}
                        WHERE id={ph}""",
                    (
                        "ignored_terminal",
                        str(row.get("job_finished_at") or current.isoformat()),
                        current.isoformat(),
                        row.get("id"),
                    ),
                )
                ignored += 1
            elif predicted_at and current - predicted_at > dt.timedelta(days=14):
                conn.execute(
                    f"""UPDATE operational_forecast_predictions SET
                        evaluation_status={ph},evaluated_at={ph}
                        WHERE id={ph}""",
                    ("expired", current.isoformat(), row.get("id")),
                )
                ignored += 1

    workload = build_workload_calibration(
        now=current,
        current_active_workers=0,
    )
    profiles = {
        str(profile.get("kind") or ""): dict(profile)
        for profile in workload.get("profiles") or []
        if profile.get("calibrated")
    }
    backlog_rows, backlog_available = _workload_rows(backlog_only=True)
    if not backlog_available:
        return {
            "available": True,
            "created": created,
            "evaluated": evaluated,
            "ignored": ignored,
        }

    min_band_samples = _int_env(
        "OPERATIONS_FORECAST_MIN_WORKLOAD_COMPLETED_JOBS",
        2,
        2,
        20,
    )
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        for job in backlog_rows:
            job_id = str(job.get("id") or "").strip()
            if not job_id:
                continue
            exists = conn.execute(
                f"SELECT 1 FROM operational_forecast_predictions WHERE job_id={ph}",
                (job_id,),
            ).fetchone()
            if exists:
                continue
            workload_kind = _workload_kind(job.get("original_name"))
            profile = profiles.get(workload_kind)
            if not profile:
                continue
            nominal = float(profile.get("medianDurationSeconds") or 0)
            conservative = float(profile.get("p95DurationSeconds") or 0)
            band = _size_band(job.get("source_bytes"))
            basis = "class_duration"
            for band_profile in profile.get("sizeBands") or []:
                if (
                    str(band_profile.get("band") or "") == band
                    and int(band_profile.get("samples") or 0) >= min_band_samples
                    and float(band_profile.get("medianDurationSeconds") or 0) > 0
                    and float(band_profile.get("p95DurationSeconds") or 0) > 0
                ):
                    nominal = float(
                        band_profile.get("medianDurationSeconds") or nominal
                    )
                    conservative = float(
                        band_profile.get("p95DurationSeconds") or conservative
                    )
                    basis = f"size_band:{band}"
                    break
            if nominal <= 0 or conservative <= 0:
                continue
            prediction = {
                "id": f"service:{job_id}",
                "job_id": job_id,
                "workload_kind": workload_kind,
                "size_band": band,
                "model_basis": basis,
                "model_version": "workload-v1",
                "sample_count": int(profile.get("completedSamples") or 0),
                "predicted_nominal_seconds": round(nominal, 3),
                "predicted_p95_seconds": round(conservative, 3),
                "predicted_at": current.isoformat(),
                "evaluation_status": "pending",
            }
            columns = tuple(prediction.keys())
            try:
                conn.execute(
                    f"INSERT INTO operational_forecast_predictions"
                    f"({','.join(columns)}) VALUES "
                    f"({','.join([ph] * len(columns))})",
                    tuple(prediction[column] for column in columns),
                )
                created += 1
            except Exception:
                existing = conn.execute(
                    f"SELECT 1 FROM operational_forecast_predictions WHERE job_id={ph}",
                    (job_id,),
                ).fetchone()
                if not existing:
                    raise

        retention = (current - dt.timedelta(days=90)).isoformat()
        conn.execute(
            f"""DELETE FROM operational_forecast_predictions
                WHERE evaluation_status<>'pending'
                  AND evaluated_at<>'' AND evaluated_at < {ph}""",
            (retention,),
        )

    return {
        "available": True,
        "created": created,
        "evaluated": evaluated,
        "ignored": ignored,
    }


def _accuracy_group(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "evaluated": 0,
            "medianAbsoluteErrorSeconds": 0.0,
            "medianAbsolutePercentageError": None,
            "meanAbsolutePercentageError": None,
            "medianSignedBias": None,
            "p95Coverage": None,
            "bias": "unknown",
        }
    absolute_errors = [
        float(row.get("nominal_absolute_error_seconds") or 0) for row in rows
    ]
    apes = [
        max(0.0, float(row.get("nominal_absolute_percentage_error") or 0))
        for row in rows
    ]
    signed = [
        float(row.get("nominal_signed_percentage_error") or 0)
        for row in rows
    ]
    covered = sum(bool(row.get("p95_covered")) for row in rows)
    median_bias = _percentile(signed, 0.5)
    bias = (
        "optimistic"
        if median_bias < -0.15
        else "conservative"
        if median_bias > 0.15
        else "balanced"
    )
    return {
        "evaluated": len(rows),
        "medianAbsoluteErrorSeconds": round(
            _percentile(absolute_errors, 0.5), 1
        ),
        "medianAbsolutePercentageError": round(
            _percentile(apes, 0.5), 4
        ),
        "meanAbsolutePercentageError": round(mean(apes), 4),
        "medianSignedBias": round(median_bias, 4),
        "p95Coverage": round(covered / len(rows), 4),
        "bias": bias,
    }


def build_forecast_accuracy(
    *,
    now: dt.datetime | None = None,
    days: int = 7,
) -> dict[str, Any]:
    """Summarize strictly pre-completion prediction error and trust signals."""
    current = _utc(now)
    window_days = max(1, min(30, int(days or 7)))
    cutoff = current - dt.timedelta(days=window_days)
    try:
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            rows = conn.execute(
                f"""SELECT * FROM operational_forecast_predictions
                    WHERE evaluation_status='evaluated'
                      AND completed_at >= {ph}
                    ORDER BY completed_at ASC""",
                (cutoff.isoformat(),),
            ).fetchall()
            pending_row = conn.execute(
                "SELECT COUNT(*) AS count FROM operational_forecast_predictions "
                "WHERE evaluation_status='pending'"
            ).fetchone()
    except Exception as exc:
        if _prediction_table_unavailable(exc):
            return {
                "available": False,
                "windowDays": window_days,
                "state": "not_started",
                "label": "尚未開始回測",
                "evaluated": 0,
                "pending": 0,
                "confidenceAdjustment": "none",
                "workloads": [],
            }
        raise

    evaluated_rows = [dict(row) for row in rows]
    summary = _accuracy_group(evaluated_rows)
    pending = int(dict(pending_row).get("count") or 0) if pending_row else 0
    minimum = _int_env(
        "OPERATIONS_FORECAST_ACCURACY_MIN_EVALUATED",
        5,
        3,
        100,
    )
    warning_error = _float_env(
        "OPERATIONS_FORECAST_ACCURACY_WARNING_ERROR_PERCENT",
        30.0,
        10.0,
        200.0,
    ) / 100.0
    high_error = _float_env(
        "OPERATIONS_FORECAST_ACCURACY_HIGH_ERROR_PERCENT",
        50.0,
        20.0,
        300.0,
    ) / 100.0
    min_p95_coverage = _float_env(
        "OPERATIONS_FORECAST_ACCURACY_MIN_P95_COVERAGE_PERCENT",
        70.0,
        30.0,
        99.0,
    ) / 100.0

    count = int(summary.get("evaluated") or 0)
    median_ape = summary.get("medianAbsolutePercentageError")
    p95_coverage = summary.get("p95Coverage")
    if count < minimum:
        state = "collecting"
        label = f"回測樣本累積中（{count}/{minimum}）"
        adjustment = "none"
    elif (
        median_ape is not None
        and median_ape >= high_error
    ) or (
        p95_coverage is not None
        and p95_coverage < max(0.4, min_p95_coverage - 0.15)
    ):
        state = "low_trust"
        label = "近期回測誤差偏高，Forecast 信心降至低"
        adjustment = "downgrade_to_low"
    elif (
        median_ape is not None
        and median_ape >= warning_error
    ) or (
        p95_coverage is not None
        and p95_coverage < min_p95_coverage
    ):
        state = "caution"
        label = "近期回測誤差上升，Forecast 信心下調一級"
        adjustment = "downgrade_one"
    else:
        state = "stable"
        label = "近期回測誤差穩定"
        adjustment = "none"

    workload_rows: dict[str, list[dict[str, Any]]] = {}
    for row in evaluated_rows:
        workload_rows.setdefault(
            str(row.get("workload_kind") or "other"), []
        ).append(row)
    workloads = []
    for kind, group in sorted(workload_rows.items()):
        item = _accuracy_group(group)
        item.update({
            "kind": kind,
            "label": _WORKLOAD_LABELS.get(kind, kind),
        })
        workloads.append(item)

    return {
        "available": True,
        "windowDays": window_days,
        "state": state,
        "label": label,
        "minimumEvaluated": minimum,
        "pending": pending,
        "confidenceAdjustment": adjustment,
        **summary,
        "workloads": workloads,
        "heuristics": {
            "warningMedianError": round(warning_error, 4),
            "highMedianError": round(high_error, 4),
            "minimumP95Coverage": round(min_p95_coverage, 4),
        },
        "note": (
            "只評分 Job 完成前已固定的 service-time prediction；"
            "未實際提交的 What-if 情境不納入準確率。"
        ),
    }


def _open_capacity_blockers() -> list[dict[str, str]]:
    blocking_codes = {
        "WORKER_OFFLINE",
        "WORKER_HEARTBEAT_STALLED",
        "R2_STORAGE",
        "GDRIVE_STORAGE",
        "MEGA_STORAGE",
        "OCI_STORAGE",
        "STORAGE_PROVIDER",
        "FFMPEG_CONVERSION",
        "LIBREOFFICE_CONVERSION",
        "DATABASE",
        "DNS_RESOLUTION",
        "TLS_CONNECTION",
        "NETWORK_TIMEOUT",
    }
    try:
        with common_db.read_connection() as (conn, _kind):
            rows = conn.execute(
                "SELECT error_code,title FROM operational_incidents "
                "WHERE status='open'"
            ).fetchall()
    except Exception as exc:
        text = str(exc or "").lower()
        if "no such table" in text or ("relation" in text and "does not exist" in text):
            return []
        raise
    blockers = []
    for raw in rows:
        row = dict(raw)
        code = str(row.get("error_code") or "").strip().upper()
        if code not in blocking_codes:
            continue
        blockers.append({
            "code": code,
            "title": str(row.get("title") or code)[:240],
        })
    return blockers


def build_capacity_forecast(
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Estimate service capacity and queue drain scenarios from real history."""
    current = _utc(now)
    window_hours = _int_env("OPERATIONS_FORECAST_WINDOW_HOURS", 6, 2, 24)
    min_completed = _int_env("OPERATIONS_FORECAST_MIN_COMPLETED_JOBS", 3, 2, 50)
    min_snapshot_coverage = _float_env(
        "OPERATIONS_FORECAST_MIN_SNAPSHOT_COVERAGE",
        0.5,
        0.25,
        1.0,
    )
    start = current - dt.timedelta(hours=window_hours)
    arrivals, arrivals_available = _job_arrival_count(start, current)
    durations = _completed_durations(start, current)
    snapshots = _snapshot_rows_since(start)
    expected_samples = window_hours * 6
    coverage = min(1.0, len(snapshots) / max(1, expected_samples))
    available_snapshots = [
        row for row in snapshots if bool(row.get("worker_status_available"))
    ]

    latest = snapshots[-1] if snapshots else {}
    latest_at = _parse_time(latest.get("sampled_at"))
    sample_age = (
        max(0, int((current - latest_at).total_seconds()))
        if latest_at
        else None
    )
    latest_fresh = sample_age is not None and sample_age <= 20 * 60
    pending = int(latest.get("pending_jobs") or 0) if latest else 0
    retry = int(latest.get("retry_jobs") or 0) if latest else 0
    processing = int(latest.get("processing_jobs") or 0) if latest else 0
    backlog = pending + retry + processing
    current_active = (
        int(latest.get("active_workers") or 0)
        if latest_fresh and bool(latest.get("worker_status_available"))
        else 0
    )
    average_active = (
        mean(int(row.get("active_workers") or 0) for row in available_snapshots)
        if available_snapshots
        else 0.0
    )

    completion_count = len(durations)
    arrival_rate = arrivals / window_hours if arrivals_available else None
    observed_completion_rate = completion_count / window_hours
    median_duration = _percentile(durations, 0.5) if durations else 0.0
    p95_duration = _percentile(durations, 0.95) if durations else 0.0
    nominal_per_worker = 3600 / median_duration if median_duration > 0 else None
    conservative_per_worker = 3600 / p95_duration if p95_duration > 0 else None

    blockers = _open_capacity_blockers()
    enough_jobs = completion_count >= min_completed
    enough_snapshots = coverage >= min_snapshot_coverage and latest_fresh
    model_available = bool(
        arrivals_available
        and enough_jobs
        and enough_snapshots
        and nominal_per_worker
        and conservative_per_worker
        and current_active > 0
    )

    confidence = "unavailable"
    reasons: list[str] = []
    if not arrivals_available:
        reasons.append("目前 schema 無法回算近期工作到達率")
    if not enough_jobs:
        reasons.append(
            f"最近 {window_hours} 小時只有 {completion_count} 筆完成工作，"
            f"至少需要 {min_completed} 筆"
        )
    if not enough_snapshots:
        reasons.append(
            f"Worker/queue 採樣覆蓋 {round(coverage * 100)}%，"
            "或最新樣本已超過 20 分鐘"
        )
    if current_active <= 0:
        reasons.append("最新可信樣本沒有在線 Worker")
    if blockers:
        reasons.append("目前仍有未排除的 Worker/provider/conversion Incident")

    if model_available:
        if blockers:
            confidence = "low"
        elif coverage >= 0.8 and completion_count >= max(5, min_completed):
            confidence = "high"
        else:
            confidence = "medium"

    raw_confidence = confidence
    prediction_accuracy = build_forecast_accuracy(now=current, days=7)
    adjustment = str(
        prediction_accuracy.get("confidenceAdjustment") or "none"
    )
    if model_available and adjustment == "downgrade_to_low":
        confidence = "low"
        reasons.append("近 7 日事前預測回測誤差偏高，模型信心已降至低。")
    elif model_available and adjustment == "downgrade_one":
        confidence = {
            "high": "medium",
            "medium": "low",
            "low": "low",
        }.get(confidence, confidence)
        reasons.append("近 7 日事前預測回測誤差上升，模型信心已下調一級。")

    def scenario(worker_count: int, per_worker: float | None) -> dict[str, Any]:
        if not model_available or not per_worker or arrival_rate is None:
            return {
                "workers": worker_count,
                "capacityPerHour": None,
                "netDrainPerHour": None,
                "clearEtaSeconds": None,
                "state": "unavailable",
            }
        total_capacity = per_worker * max(0, worker_count)
        net = total_capacity - arrival_rate
        eta = (backlog / net * 3600) if backlog > 0 and net > 0 else 0 if backlog == 0 else None
        return {
            "workers": worker_count,
            "capacityPerHour": round(total_capacity, 2),
            "netDrainPerHour": round(net, 2),
            "clearEtaSeconds": round(eta) if eta is not None else None,
            "state": "clearing" if net > 0 else "growing",
        }

    current_nominal = scenario(current_active, nominal_per_worker)
    current_conservative = scenario(current_active, conservative_per_worker)
    plus_one_nominal = scenario(current_active + 1, nominal_per_worker)
    plus_one_conservative = scenario(current_active + 1, conservative_per_worker)

    workload_calibration = build_workload_calibration(
        now=current,
        window_hours=window_hours,
        current_active_workers=current_active,
    )

    decision_state = "insufficient_data"
    decision_label = "資料不足，先累積真實吞吐量"
    decision_detail = "目前不應根據不完整樣本決定是否增加 Worker。"
    if blockers:
        decision_state = "dependency_blocked"
        decision_label = "先排除故障，再判斷容量"
        decision_detail = (
            "目前存在 Worker/provider/conversion Incident，處理速度可能被故障拖慢；"
            "此時擴充 Worker 不一定能改善根因。"
        )
    elif model_available and backlog == 0:
        decision_state = "no_backlog"
        decision_label = "目前沒有待清 Queue"
        decision_detail = "目前沒有 backlog，先持續累積高峰期資料再做容量決策。"
    elif model_available and current_conservative["state"] == "clearing":
        decision_state = "current_capacity_clearing"
        decision_label = "目前容量在保守情境仍可消化 Queue"
        decision_detail = (
            "以近期 P95 處理時間估算，現有在線 Worker 的完成能力仍高於近期到達率。"
        )
    elif (
        model_available
        and current_nominal["state"] == "clearing"
        and current_conservative["state"] == "growing"
    ):
        decision_state = "borderline"
        decision_label = "目前容量接近臨界"
        decision_detail = (
            "以中位處理時間可清 Queue，但用 P95 保守估算時到達率可能超過處理能力；"
            "建議先觀察下一個高峰時段。"
        )
    elif (
        model_available
        and current_nominal["state"] == "growing"
        and plus_one_conservative["state"] == "clearing"
    ):
        decision_state = "one_more_worker_would_restore_drain"
        decision_label = "多 1 台 Worker 的模型可恢復淨消化能力"
        decision_detail = (
            "現有容量的 nominal 模型已低於近期到達率，而增加 1 台後連 P95 保守情境也可清 Queue。"
        )
    elif (
        model_available
        and plus_one_nominal["state"] == "clearing"
    ):
        decision_state = "one_more_worker_may_help"
        decision_label = "多 1 台 Worker 可能改善高峰 Queue"
        decision_detail = (
            "增加 1 台後 nominal 模型可恢復淨消化，但保守 P95 情境仍不足；"
            "需先確認工作類型與依賴沒有持續變慢。"
        )
    elif model_available:
        decision_state = "one_more_worker_insufficient"
        decision_label = "單純增加 1 台 Worker 仍不足"
        decision_detail = (
            "即使多 1 台 Worker，近期到達率仍不低於估計處理能力；"
            "應同時檢查工作尖峰、單 Job 耗時與 provider 吞吐。"
        )

    return {
        "generatedAt": current.isoformat(),
        "windowHours": window_hours,
        "modelAvailable": model_available,
        "rawConfidence": raw_confidence,
        "confidence": confidence,
        "predictionCalibration": prediction_accuracy,
        "limitations": reasons,
        "sample": {
            "arrivals": arrivals if arrivals_available else None,
            "completedJobs": completion_count,
            "snapshotCount": len(snapshots),
            "expectedSnapshotCount": expected_samples,
            "snapshotCoverage": round(coverage, 4),
            "latestSampleAt": latest_at.isoformat() if latest_at else "",
            "latestSampleAgeSeconds": sample_age,
        },
        "rates": {
            "arrivalPerHour": round(arrival_rate, 2) if arrival_rate is not None else None,
            "observedCompletedPerHour": round(observed_completion_rate, 2),
            "medianCompletedDurationSeconds": round(median_duration, 1) if median_duration else 0.0,
            "p95CompletedDurationSeconds": round(p95_duration, 1) if p95_duration else 0.0,
            "nominalPerWorkerPerHour": round(nominal_per_worker, 2)
            if nominal_per_worker
            else None,
            "conservativePerWorkerPerHour": round(conservative_per_worker, 2)
            if conservative_per_worker
            else None,
            "averageActiveWorkers": round(average_active, 2),
        },
        "queue": {
            "pending": pending,
            "retry": retry,
            "processing": processing,
            "backlogJobs": backlog,
            "currentActiveWorkers": current_active,
        },
        "blockers": blockers,
        "current": {
            "nominal": current_nominal,
            "conservative": current_conservative,
        },
        "plusOneWorker": {
            "nominal": plus_one_nominal,
            "conservative": plus_one_conservative,
        },
        "workloadCalibration": workload_calibration,
        "decision": {
            "state": decision_state,
            "label": decision_label,
            "detail": decision_detail,
        },
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
        "capacityForecast": build_capacity_forecast(now=current),
        "series": series,
    }


__all__ = [
    "analyze_operational_trends",
    "build_capacity_forecast",
    "build_forecast_accuracy",
    "build_workload_calibration",
    "simulate_capacity_what_if",
    "build_operational_dashboard",
    "reconcile_forecast_predictions",
    "record_operational_sample",
    "trend_incident_candidates",
]
