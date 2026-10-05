"""Canonical material-worker operational projections and staging cleanup."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from typing import Callable

from teacher_app.storage import r2_budget
from teacher_app.worker import error_observability, repository


LOGGER = logging.getLogger(__name__)
WORKER_STATUS_ERROR = "無法讀取本機 Worker 狀態，請稍後再試或檢查伺服器記錄。"


def _parse_utc(value: object) -> dt.datetime | None:
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


def material_job_observability(
    job: dict,
    *,
    now: dt.datetime | None = None,
    stale_seconds: int | None = None,
    heartbeat_warning_seconds: int | None = None,
) -> dict:
    """Attach one human-facing liveness projection without changing queue state."""
    item = dict(job or {})
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)

    heartbeat_interval = _int_env("MATERIAL_WORKER_HEARTBEAT_SECONDS", 30, 5, 90)
    warning_seconds = (
        max(90, heartbeat_interval * 4)
        if heartbeat_warning_seconds is None
        else max(30, int(heartbeat_warning_seconds))
    )
    stale_limit = (
        _int_env("MATERIAL_JOB_STALE_SECONDS", 1800, 300, 21600)
        if stale_seconds is None
        else max(300, min(21600, int(stale_seconds)))
    )

    status_value = str(item.get("status") or "")
    started = _parse_utc(item.get("startedAt") or item.get("createdAt"))
    finished = _parse_utc(item.get("finishedAt"))
    elapsed_end = finished or current
    elapsed_seconds = (
        max(0, int((elapsed_end - started).total_seconds()))
        if started
        else 0
    )

    heartbeat = _parse_utc(item.get("workerLastSeen"))
    if heartbeat is None and status_value == "processing":
        heartbeat = _parse_utc(item.get("updatedAt"))
    heartbeat_age = (
        max(0, int((current - heartbeat).total_seconds()))
        if heartbeat
        else None
    )

    available = _parse_utc(item.get("availableAt"))
    retry_in = (
        max(0, int((available - current).total_seconds()))
        if status_value == "retry_wait" and available
        else 0
    )

    state = "unknown"
    label = "狀態待確認"
    detail = ""
    if status_value == "processing":
        if heartbeat_age is None:
            state = "heartbeat_delayed"
            label = "等待 Worker 回報"
            detail = "工作正在處理，但尚未取得本輪 heartbeat；不會僅因處理時間較長就判定失敗。"
        elif heartbeat_age >= stale_limit:
            state = "stalled"
            label = "可能卡住"
            detail = f"Worker 已 {heartbeat_age} 秒沒有回報；達到 stale 門檻 {stale_limit} 秒。"
        elif heartbeat_age >= warning_seconds:
            state = "heartbeat_delayed"
            label = "回報延遲"
            detail = f"Worker 已 {heartbeat_age} 秒沒有回報；未達 stale 門檻 {stale_limit} 秒。"
        else:
            state = "active"
            label = "持續處理"
            detail = f"Worker heartbeat 正常（{heartbeat_age} 秒前）；即使處理時間較長也不視為卡住。"
    elif status_value == "retry_wait":
        state = "retry_wait"
        label = "等待重試"
        detail = (
            f"預計 {retry_in} 秒後可再次由 Worker 領取。"
            if retry_in
            else "已到可重試時間，等待可用 Worker 領取。"
        )
    elif status_value == "queued":
        state = "queued"
        label = "等待 Worker"
        detail = "原始檔已安全排隊，尚未由 Worker 領取。"
    elif status_value == "completed":
        state = "completed"
        label = "已完成"
        detail = "教材已完成正式發布。"
    elif status_value == "failed":
        state = "failed"
        label = "需要處理"
        detail = str(item.get("error") or item.get("detail") or "背景工作失敗。")[:500]
    elif status_value == "cancelled":
        state = "cancelled"
        label = "已取消"
        detail = str(item.get("detail") or "背景工作已取消。")[:500]

    item.update(
        {
            "elapsedSeconds": elapsed_seconds,
            "heartbeatAgeSeconds": heartbeat_age,
            "heartbeatWarningSeconds": warning_seconds,
            "staleThresholdSeconds": stale_limit,
            "retryInSeconds": retry_in,
            "observabilityState": state,
            "observabilityLabel": label,
            "observabilityDetail": detail,
            "heartbeatDelayed": state == "heartbeat_delayed",
            "stalled": state == "stalled",
        }
    )
    item.update(
        error_observability.classify_material_error(
            item.get("error"),
            stage=item.get("stage"),
            status=status_value,
            observability_state=state,
        )
    )
    return item


def material_jobs_observability(
    jobs,
    *,
    now: dt.datetime | None = None,
    stale_seconds: int | None = None,
    heartbeat_warning_seconds: int | None = None,
) -> list[dict]:
    current = now or dt.datetime.now(dt.timezone.utc)
    return [
        material_job_observability(
            item,
            now=current,
            stale_seconds=stale_seconds,
            heartbeat_warning_seconds=heartbeat_warning_seconds,
        )
        for item in (jobs or [])
    ]


def _env_true(name: str, default: bool) -> bool:
    fallback = "true" if default else "false"
    return os.environ.get(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _worker_machine_key(worker_id: str, capabilities: dict | None = None) -> str:
    """Return a stable physical-host key across legacy Worker ID formats."""
    caps = capabilities or {}
    machine = str(caps.get("workerMachine") or "").strip().lower()
    if machine:
        return machine
    raw = str(worker_id or "").strip()
    lowered = raw.lower()
    marker = "-teacherworker"
    if marker in lowered:
        return lowered.split(marker, 1)[0]
    if ":" in lowered:
        return lowered.split(":", 1)[0]
    return lowered


def _latest_heartbeat_per_machine(rows) -> list[tuple[dict, dict, dt.datetime]]:
    """Keep only the freshest heartbeat for each physical machine.

    Old IDs from reinstall/reconfiguration must not create duplicate online
    cards or false offline alerts after the same PC reconnects with a new ID.
    """
    latest: dict[str, tuple[dict, dict, dt.datetime]] = {}
    for item in rows:
        worker_id = str(item.get("worker_id") or item.get("workerId") or "").strip()
        last_seen = str(item.get("last_seen") or item.get("lastSeen") or "").strip()
        if not worker_id or not last_seen:
            continue
        try:
            seen = dt.datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=dt.timezone.utc)
            seen = seen.astimezone(dt.timezone.utc)
        except (TypeError, ValueError):
            continue
        raw = item.get("capabilities") or {}
        try:
            capabilities = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (TypeError, ValueError):
            capabilities = {}
        # AI Worker heartbeats share the durable heartbeat table for service
        # readiness, but must never appear as duplicate material Workers or
        # influence material offline/recovery decisions.
        if str(capabilities.get("workerKind") or "material").strip().lower() == "ai":
            continue
        key = _worker_machine_key(worker_id, capabilities) or worker_id.lower()
        current = latest.get(key)
        if current is None or seen > current[2]:
            latest[key] = (dict(item), capabilities, seen)
    return list(latest.values())



def online_worker_recovery_keys(
    *,
    now: dt.datetime | None = None,
    connection_factory=None,
) -> set[str]:
    """Return stable machine/worker identifiers with a confirmed fresh heartbeat."""
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)
    cutoff = current - dt.timedelta(seconds=120)
    try:
        heartbeats = repository.list_heartbeats(
            50,
            connection_factory=connection_factory,
        )
    except Exception:
        LOGGER.exception("Worker heartbeat recovery lookup failed")
        return set()
    keys: set[str] = set()
    for item, capabilities, seen in _latest_heartbeat_per_machine(heartbeats):
        if seen < cutoff:
            continue
        worker_id = str(item.get("worker_id") or item.get("workerId") or "").strip()
        machine_key = _worker_machine_key(worker_id, capabilities)
        if machine_key:
            keys.add(machine_key)
        if worker_id:
            keys.add(worker_id.lower())
    return keys



def offline_worker_alerts(
    *,
    now: dt.datetime | None = None,
    connection_factory=None,
) -> dict:
    """Project confirmed prolonged Worker heartbeat outages for notifications.

    A heartbeat repository failure is reported as unavailable and never treated
    as an offline Worker. Short transient gaps remain visible in Worker status
    but do not become alert events until the bounded alert threshold is crossed.
    """
    if not _env_true("MATERIAL_WORKER_ENABLED", True):
        return {"available": True, "thresholdSeconds": 0, "workers": []}

    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)
    threshold_seconds = _int_env(
        "MATERIAL_WORKER_OFFLINE_ALERT_SECONDS", 600, 300, 3600
    )
    retention_hours = _int_env(
        "MATERIAL_WORKER_HEARTBEAT_RETENTION_HOURS", 24, 1, 720
    )
    history_cutoff = current - dt.timedelta(hours=retention_hours)

    try:
        heartbeats = repository.list_heartbeats(
            50, connection_factory=connection_factory
        )
    except Exception:
        LOGGER.exception("Worker heartbeat alert lookup failed")
        return {
            "available": False,
            "thresholdSeconds": threshold_seconds,
            "workers": [],
        }

    workers = []
    for item, capabilities, seen in _latest_heartbeat_per_machine(heartbeats):
        worker_id = str(item.get("worker_id") or item.get("workerId") or "").strip()
        if seen < history_cutoff:
            continue
        offline_seconds = max(0, int((current - seen).total_seconds()))
        if offline_seconds < threshold_seconds:
            continue
        workers.append(
            {
                "workerId": worker_id,
                "workerMachine": str(capabilities.get("workerMachine") or "")[:80],
                "lastSeen": seen.isoformat(),
                "offlineSeconds": offline_seconds,
                "currentJobId": str(
                    item.get("current_job_id") or item.get("currentJobId") or ""
                ),
            }
        )
    workers.sort(key=lambda row: (-int(row["offlineSeconds"]), row["workerId"]))
    return {
        "available": True,
        "thresholdSeconds": threshold_seconds,
        "workers": workers,
    }



def operational_incident_candidates(
    *,
    now: dt.datetime | None = None,
    connection_factory=None,
) -> list[dict]:
    """Project only confirmed operational conditions worth incidenting."""
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)
    candidates: list[dict] = []

    offline = offline_worker_alerts(
        now=current,
        connection_factory=connection_factory,
    )
    if offline.get("available"):
        threshold_minutes = max(1, int(offline.get("thresholdSeconds") or 0) // 60)
        for worker in offline.get("workers") or []:
            worker_id = str(worker.get("workerId") or "").strip()
            machine = str(worker.get("workerMachine") or "").strip().lower()
            resource = machine or worker_id.lower()
            if not resource:
                continue
            offline_minutes = max(1, int(worker.get("offlineSeconds") or 0) // 60)
            candidates.append({
                "incidentKey": f"worker_offline:{resource}",
                "incidentType": "worker_offline",
                "category": "worker",
                "severity": "critical",
                "title": "教材 Worker 已離線",
                "detail": (
                    f"{worker_id or resource} 已超過 {threshold_minutes} 分鐘未回報心跳；"
                    f"目前約離線 {offline_minutes} 分鐘。"
                ),
                "action": "啟動或重新啟動院內 Worker；已排隊與 R2 staging 的教材不需要重新上傳。",
                "errorCode": "WORKER_OFFLINE",
                "resourceId": worker_id or resource,
            })

    jobs = material_jobs_observability(
        repository.list_material_jobs(
            100,
            connection_factory=connection_factory,
        ),
        now=current,
    )
    for job in jobs:
        if job.get("observabilityState") != "stalled":
            continue
        job_id = str(job.get("id") or "").strip()
        if not job_id:
            continue
        candidates.append({
            "incidentKey": f"job_stalled:{job_id}",
            "incidentType": "job_stalled",
            "category": "worker",
            "severity": "critical",
            "title": "教材處理工作可能卡住",
            "detail": (
                f"{job.get('title') or job.get('originalName') or job_id} 已超過 "
                f"{int(job.get('staleThresholdSeconds') or 0)} 秒未收到 Worker heartbeat。"
            ),
            "action": "先確認院內 Worker 是否仍在執行；系統會依 stale recovery 安全續接，請勿重複上傳。",
            "errorCode": "WORKER_HEARTBEAT_STALLED",
            "resourceId": job_id,
        })

    terminal = [
        job for job in jobs
        if str(job.get("status") or "") in {"completed", "failed"}
    ]
    min_jobs = _int_env("MATERIAL_INCIDENT_FAILURE_RATE_MIN_JOBS", 5, 3, 50)
    rate_percent = _int_env("MATERIAL_INCIDENT_FAILURE_RATE_PERCENT", 50, 20, 100)
    sample = terminal[:20]
    failures = [job for job in sample if str(job.get("status") or "") == "failed"]
    if len(sample) >= min_jobs and failures:
        rate = len(failures) / len(sample)
        if rate * 100 >= rate_percent:
            candidates.append({
                "incidentKey": "material_failure_rate",
                "incidentType": "failure_rate",
                "category": "worker",
                "severity": "warning",
                "title": "教材背景工作近期失敗率偏高",
                "detail": (
                    f"最近 {len(sample)} 筆完成/失敗工作中有 {len(failures)} 筆失敗，"
                    f"失敗率約 {round(rate * 100)}%。"
                ),
                "action": "先查看近期 error code 分布與 Worker/儲存狀態，再決定是否需要人工介入。",
                "errorCode": "MATERIAL_FAILURE_RATE_HIGH",
                "resourceId": "material-jobs",
            })

    burst_threshold = _int_env("MATERIAL_INCIDENT_ERROR_BURST_COUNT", 3, 2, 10)
    burst_codes = {
        "R2_STORAGE",
        "GDRIVE_STORAGE",
        "MEGA_STORAGE",
        "OCI_STORAGE",
        "STORAGE_PROVIDER",
        "FFMPEG_CONVERSION",
        "LIBREOFFICE_CONVERSION",
    }
    run_code = ""
    run_count = 0
    for job in terminal:
        if str(job.get("status") or "") == "completed":
            break
        code = str(job.get("errorCode") or "")
        if code not in burst_codes:
            break
        if not run_code:
            run_code = code
            run_count = 1
        elif code == run_code:
            run_count += 1
        else:
            break
    if run_code and run_count >= burst_threshold:
        sample_job = next(
            (job for job in terminal if str(job.get("errorCode") or "") == run_code),
            {},
        )
        candidates.append({
            "incidentKey": f"error_burst:{run_code.lower()}",
            "incidentType": "error_burst",
            "category": str(sample_job.get("errorCategory") or "worker"),
            "severity": "critical" if run_count >= burst_threshold + 1 else "warning",
            "title": f"教材背景工作連續發生 {run_code}",
            "detail": f"最近已連續 {run_count} 筆工作以相同 error code 失敗。",
            "action": str(sample_job.get("errorAction") or "先查看 Worker / Job 狀態與技術細節，再恢復處理。"),
            "errorCode": run_code,
            "resourceId": run_code,
        })

    return candidates



def cleanup_staging(
    delete_staging: Callable[[dict], None],
    *,
    connection_factory=None,
) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    failed_retention = r2_budget.R2BudgetPolicy.from_env().failed_retention_hours
    standard_retention = _int_env("MATERIAL_JOB_RETENTION_HOURS", 72, 6, 720)
    for job in repository.list_cleanup_candidates(connection_factory=connection_factory):
        retention = failed_retention if job.get("status") == "failed" else standard_retention
        try:
            updated = dt.datetime.fromisoformat(
                str(job.get("updatedAt") or "").replace("Z", "+00:00")
            )
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=dt.timezone.utc)
        except (TypeError, ValueError):
            updated = None
        due = bool(updated and updated <= now - dt.timedelta(hours=retention))
        if not due and not bool(job.get("cleanupPending")):
            continue
        try:
            delete_staging(job)
        except Exception as exc:
            LOGGER.warning(
                "material staging cleanup failed job_id=%s backend=%s error_type=%s",
                str(job.get("id") or "")[:80],
                str(job.get("stagingBackend") or "")[:32],
                type(exc).__name__,
            )
            repository.update_material_job(
                str(job.get("id") or ""),
                fields={"cleanup_pending": True, "updated_at": now.isoformat()},
                connection_factory=connection_factory,
            )
            continue
        repository.update_material_job(
            str(job.get("id") or ""),
            fields={
                "staging_path": "",
                "staging_key": "",
                "cleanup_pending": False,
                "updated_at": now.isoformat(),
            },
            connection_factory=connection_factory,
        )


def recover_stale_processing_jobs(
    staging_exists: Callable[[dict], bool],
    *,
    stale_seconds: int | None = None,
    connection_factory=None,
    now: dt.datetime | None = None,
) -> dict[str, int]:
    """Recover stale processing rows without racing a fresh Worker heartbeat."""

    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    seconds = (
        _int_env("MATERIAL_JOB_STALE_SECONDS", 1800, 300, 21600)
        if stale_seconds is None
        else max(300, min(21600, int(stale_seconds)))
    )
    threshold = (current - dt.timedelta(seconds=seconds)).isoformat()
    stamp = current.isoformat()
    counts = {"requeued": 0, "failed": 0, "lostRace": 0}

    for job in repository.list_stale_processing_jobs(
        threshold,
        connection_factory=connection_factory,
    ):
        job_id = str(job.get("id") or "")
        worker_id = str(job.get("workerId") or "")
        updated_at = str(job.get("updatedAt") or "")
        try:
            has_staging = bool(staging_exists(job))
        except Exception as exc:
            counts["stagingProbeErrors"] = counts.get("stagingProbeErrors", 0) + 1
            LOGGER.warning(
                "stale material staging probe failed job_id=%s backend=%s error_type=%s",
                job_id[:80],
                str(job.get("stagingBackend") or "")[:32],
                type(exc).__name__,
            )
            # Fail closed on uncertainty: a storage/provider outage is not proof
            # that the retained source disappeared. Leave ownership/status intact
            # so the next recovery cycle can make an authoritative decision.
            continue

        if has_staging:
            fields = {
                "status": "queued",
                "available_at": stamp,
                "updated_at": stamp,
                "started_at": "",
                "finished_at": "",
                "stage": "重新排隊",
                "detail": "偵測到前次 Worker 中斷，已自動續接",
                "error": "",
                "worker_id": "",
                "worker_last_seen": "",
            }
            counter = "requeued"
        else:
            fields = {
                "status": "failed",
                "updated_at": stamp,
                "finished_at": stamp,
                "stage": "處理失敗",
                "detail": "背景工作中斷且暫存原始檔已不存在，請重新上傳",
                "error": "背景工作中斷且暫存原始檔已不存在，請重新上傳",
                "worker_id": "",
                "worker_last_seen": "",
            }
            counter = "failed"

        changed = repository.cas_material_job(
            job_id,
            expected_statuses=("processing",),
            expected_worker_id=worker_id,
            expected_updated_at=updated_at,
            fields=fields,
            connection_factory=connection_factory,
        )
        if changed:
            counts[counter] += 1
        else:
            counts["lostRace"] += 1
    return counts


def status(
    staging_capability: Callable[[], dict],
    *,
    connection_factory=None,
) -> dict:
    aggregates = repository.queue_aggregates(connection_factory=connection_factory)
    pending = sum(
        int((aggregates.get(state) or {}).get("count") or 0)
        for state in ("queued", "retry_wait")
    )
    processing = int((aggregates.get("processing") or {}).get("count") or 0)
    failed_total = int((aggregates.get("failed") or {}).get("count") or 0)
    now = dt.datetime.now(dt.timezone.utc)
    recent_jobs = material_jobs_observability(
        repository.list_material_jobs(
            100,
            connection_factory=connection_factory,
        ),
        now=now,
    )
    metrics_window_hours = _int_env("MATERIAL_JOB_METRICS_WINDOW_HOURS", 24, 1, 168)
    metrics_cutoff = now - dt.timedelta(hours=metrics_window_hours)
    terminal_jobs = [
        item
        for item in recent_jobs
        if str(item.get("status") or "") in {"completed", "failed"}
        and (_parse_utc(item.get("finishedAt") or item.get("updatedAt")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)) >= metrics_cutoff
    ]
    failure_attention_hours = _int_env("MATERIAL_FAILED_ATTENTION_HOURS", 24, 1, 168)
    failure_attention_cutoff = now - dt.timedelta(hours=failure_attention_hours)
    failed_attention_jobs = [
        item for item in recent_jobs
        if str(item.get("status") or "") == "failed"
        and (_parse_utc(item.get("updatedAt") or item.get("finishedAt")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)) >= failure_attention_cutoff
    ]
    recent_failed = sum(
        str(item.get("status") or "") == "failed"
        for item in terminal_jobs
    )
    failure_rate = (
        round(recent_failed / len(terminal_jobs), 3)
        if terminal_jobs
        else 0.0
    )
    durations: list[float] = []
    for item in recent_jobs:
        if str(item.get("status") or "") != "completed":
            continue
        if (_parse_utc(item.get("finishedAt") or item.get("updatedAt")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)) < metrics_cutoff:
            continue
        try:
            started = dt.datetime.fromisoformat(
                str(item.get("startedAt") or "").replace("Z", "+00:00")
            )
            finished = dt.datetime.fromisoformat(
                str(item.get("finishedAt") or "").replace("Z", "+00:00")
            )
            if started.tzinfo is None:
                started = started.replace(tzinfo=dt.timezone.utc)
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=dt.timezone.utc)
            seconds = (finished - started).total_seconds()
            if 0 <= seconds <= 7 * 24 * 3600:
                durations.append(seconds)
        except (TypeError, ValueError):
            continue
    oldest = min(
        (
            str((aggregates.get(state) or {}).get("oldest") or "")
            for state in ("queued", "retry_wait")
            if (aggregates.get(state) or {}).get("oldest")
        ),
        default="",
    )
    oldest_age = 0
    if oldest:
        try:
            parsed = dt.datetime.fromisoformat(oldest.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            oldest_age = max(
                0,
                int((now - parsed.astimezone(dt.timezone.utc)).total_seconds()),
            )
        except (TypeError, ValueError):
            pass

    workers = []
    worker_status_available = True
    worker_status_error = ""
    try:
        cutoff = now - dt.timedelta(seconds=120)
        retention_hours = _int_env(
            "MATERIAL_WORKER_HEARTBEAT_RETENTION_HOURS", 24, 1, 720
        )
        history_cutoff = now - dt.timedelta(hours=retention_hours)
        heartbeats = repository.list_heartbeats(
            50, connection_factory=connection_factory
        )
        for item, capabilities, seen in _latest_heartbeat_per_machine(heartbeats):
            if seen < history_cutoff:
                continue
            online = seen >= cutoff
            last_seen = seen.isoformat()
            current_job = str(
                item.get("current_job_id") or item.get("currentJobId") or ""
            )
            workers.append(
                {
                    "workerId": str(item.get("worker_id") or item.get("workerId") or ""),
                    "workerMachine": str(capabilities.get("workerMachine") or "")[:80],
                    "lastSeen": last_seen,
                    "currentJobId": current_job,
                    "status": "busy" if online and current_job else ("online" if online else "offline"),
                    "ffmpeg": bool((capabilities.get("ffmpeg") or {}).get("available")),
                    "libreOffice": bool(
                        (capabilities.get("libreOffice") or {}).get("available")
                    ),
                    "workerVersion": str(capabilities.get("workerVersion") or "")[:32],
                    "workerSha": str(capabilities.get("workerSha") or "")[:40],
                    "workerBranch": str(capabilities.get("workerBranch") or "")[:80],
                    "updateAvailable": bool(capabilities.get("updateAvailable", False)),
                    "lastUpdateCheckAt": str(
                        capabilities.get("lastUpdateCheckAt") or ""
                    )[:64],
                }
            )
    except Exception:
        worker_status_available = False
        worker_status_error = WORKER_STATUS_ERROR
        workers = []
        LOGGER.exception("Worker heartbeat status lookup failed")

    active_worker_count = sum(
        item.get("status") in {"online", "busy"} for item in workers
    )
    operational_issues: list[dict] = []
    if not worker_status_available:
        operational_issues.append(
            {
                "code": "WORKER_STATUS_UNAVAILABLE",
                "category": "worker",
                "message": "目前無法讀取 Worker heartbeat 狀態",
                "action": "檢查 Web/資料庫狀態後再重新整理；此狀態本身不代表 Worker 已離線。",
            }
        )
    elif active_worker_count == 0 and (pending > 0 or processing > 0):
        operational_issues.append(
            {
                "code": "WORKER_OFFLINE",
                "category": "worker",
                "message": "目前沒有在線 Worker 可處理教材",
                "action": "啟動或重新啟動院內 Worker；已排隊/R2 staging 的教材不需要重新上傳。",
            }
        )

    stalled_count = sum(
        item.get("observabilityState") == "stalled" for item in recent_jobs
    )
    if stalled_count:
        operational_issues.append(
            {
                "code": "WORKER_JOB_STALLED",
                "category": "worker",
                "message": f"{stalled_count} 筆教材工作可能卡住",
                "action": "先確認 Worker heartbeat；系統會依既有 stale recovery 處理，避免手動建立重複工作。",
            }
        )

    return {
        "backgroundJobsEnabled": _env_true("MATERIAL_BACKGROUND_JOBS", True),
        "workerEnabled": _env_true("MATERIAL_WORKER_ENABLED", True),
        "pendingJobs": pending,
        "processingJobs": processing,
        "retryJobs": int((aggregates.get("retry_wait") or {}).get("count") or 0),
        "failedJobs": len(failed_attention_jobs),
        "failedJobsTotal": failed_total,
        "failedAttentionHours": failure_attention_hours,
        "oldestPendingAt": oldest,
        "oldestPendingAgeSeconds": oldest_age,
        "recentTerminalJobs": len(terminal_jobs),
        "metricsWindowHours": metrics_window_hours,
        "recentFailureRate": failure_rate,
        "averageCompletedDurationSeconds": (
            round(sum(durations) / len(durations), 1)
            if durations
            else 0.0
        ),
        "healthyProcessingJobs": sum(
            item.get("observabilityState") == "active" for item in recent_jobs
        ),
        "heartbeatDelayedJobs": sum(
            item.get("observabilityState") == "heartbeat_delayed" for item in recent_jobs
        ),
        "stalledJobs": stalled_count,
        "heartbeatWarningSeconds": max(
            90,
            _int_env("MATERIAL_WORKER_HEARTBEAT_SECONDS", 30, 5, 90) * 4,
        ),
        "staleThresholdSeconds": _int_env(
            "MATERIAL_JOB_STALE_SECONDS", 1800, 300, 21600
        ),
        "operationalIssues": operational_issues,
        "recentErrorCodes": sorted(
            {
                str(item.get("errorCode") or "")
                for item in recent_jobs
                if str(item.get("errorCode") or "")
            }
        ),
        "workers": workers,
        "workerStatusAvailable": worker_status_available,
        "workerStatusError": worker_status_error,
        "staging": staging_capability(),
        "r2Budget": r2_budget.status(),
    }


__all__ = [
    "WORKER_STATUS_ERROR",
    "cleanup_staging",
    "material_job_observability",
    "material_jobs_observability",
    "offline_worker_alerts",
    "online_worker_recovery_keys",
    "operational_incident_candidates",
    "recover_stale_processing_jobs",
    "status",
]
