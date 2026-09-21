"""Canonical material-worker operational projections and staging cleanup."""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Callable

from teacher_app.storage import r2_budget
from teacher_app.worker import repository


def _env_true(name: str, default: bool) -> bool:
    fallback = "true" if default else "false"
    return os.environ.get(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


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
        except Exception:
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
        except Exception:
            has_staging = False

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
            # A fresh heartbeat/ownership transition changed updated_at or owner
            # after our stale snapshot; never overwrite that newer state.
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
    failed = int((aggregates.get("failed") or {}).get("count") or 0)
    recent_jobs = repository.list_material_jobs(
        100,
        connection_factory=connection_factory,
    )
    terminal_jobs = [
        item
        for item in recent_jobs
        if str(item.get("status") or "") in {"completed", "failed"}
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
                int((dt.datetime.now(dt.timezone.utc) - parsed).total_seconds()),
            )
        except (TypeError, ValueError):
            pass

    workers = []
    try:
        now = dt.datetime.now(dt.timezone.utc)
        cutoff = now - dt.timedelta(seconds=120)
        retention_hours = _int_env(
            "MATERIAL_WORKER_HEARTBEAT_RETENTION_HOURS", 24, 1, 720
        )
        history_cutoff = now - dt.timedelta(hours=retention_hours)
        for item in repository.list_heartbeats(
            50, connection_factory=connection_factory
        ):
            last_seen = str(item.get("last_seen") or item.get("lastSeen") or "")
            try:
                seen = dt.datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                if seen.tzinfo is None:
                    seen = seen.replace(tzinfo=dt.timezone.utc)
            except (TypeError, ValueError):
                continue
            if seen < history_cutoff:
                continue
            online = seen >= cutoff
            raw = item.get("capabilities") or {}
            try:
                capabilities = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except (TypeError, ValueError):
                capabilities = {}
            current_job = str(
                item.get("current_job_id") or item.get("currentJobId") or ""
            )
            workers.append(
                {
                    "workerId": str(item.get("worker_id") or item.get("workerId") or ""),
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
        workers = []

    return {
        "backgroundJobsEnabled": _env_true("MATERIAL_BACKGROUND_JOBS", True),
        "workerEnabled": _env_true("MATERIAL_WORKER_ENABLED", True),
        "pendingJobs": pending,
        "processingJobs": processing,
        "retryJobs": int((aggregates.get("retry_wait") or {}).get("count") or 0),
        "failedJobs": failed,
        "oldestPendingAt": oldest,
        "oldestPendingAgeSeconds": oldest_age,
        "recentTerminalJobs": len(terminal_jobs),
        "recentFailureRate": failure_rate,
        "averageCompletedDurationSeconds": (
            round(sum(durations) / len(durations), 1)
            if durations
            else 0.0
        ),
        "workers": workers,
        "staging": staging_capability(),
        "r2Budget": r2_budget.status(),
    }


__all__ = ["cleanup_staging", "recover_stale_processing_jobs", "status"]