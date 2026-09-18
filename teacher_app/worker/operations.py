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
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=120)
        for item in repository.list_heartbeats(
            50, connection_factory=connection_factory
        ):
            last_seen = str(item.get("last_seen") or item.get("lastSeen") or "")
            try:
                seen = dt.datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                if seen.tzinfo is None:
                    seen = seen.replace(tzinfo=dt.timezone.utc)
                online = seen >= cutoff
            except (TypeError, ValueError):
                online = False
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
        "workers": workers,
        "staging": staging_capability(),
        "r2Budget": r2_budget.status(),
    }


__all__ = ["cleanup_staging", "status"]
