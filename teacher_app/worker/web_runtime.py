"""Narrow Web runtime seam for the material-worker HTTP boundary.

Queue/upload-session persistence is canonical in :mod:`teacher_app.worker.repository`.
Provider credentials/clients and the R2 usage ledger are canonical in
``teacher_app.storage``.  The callbacks here cover only the remaining legacy Web
orchestration clusters (R2 budget reservations, shared staging, result commit,
and media-processing metadata mirroring) until those owners are extracted.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from teacher_app.config import storage_paths
from teacher_app.materials import job_commit
from teacher_app.materials.staging_runtime import MaterialStagingRuntime
from teacher_app.storage import providers, r2_ledger
from teacher_app.storage import r2_budget
from teacher_app.worker import media_metadata, operations


ConnectionFactory = Callable[[], tuple[Any, str]]


def _env_true(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _missing(name: str):
    def missing(*_args, **_kwargs):
        raise RuntimeError(f"WorkerWebRuntime callback is not configured: {name}")

    return missing


@dataclass
class WorkerWebRuntime:
    """Explicit callbacks/config required by worker Web routes."""

    cleanup_budget_state: Callable[[], Any]
    enforce_large_upload_budget: Callable[[str, str, int], Any]
    release_reservation: Callable[[str, str], Any]
    budget_status: Callable[[], dict]
    download_staging: Callable[[dict, Path], Any]
    delete_staging: Callable[[dict], Any]
    commit_result: Callable[[dict, dict], dict]
    sync_media_processing_metadata: Callable[..., Any]
    connection_factory: ConnectionFactory | None = None
    worker_token: str | Callable[[], str] = ""
    direct_upload_enabled: bool | Callable[[], bool] = False
    direct_upload_max_mb: int | Callable[[], int] = 2048
    worker_url_ttl_seconds: int | Callable[[], int] = 900
    max_attempts: int | Callable[[], int] = 3
    r2_client_factory: Callable[[], Any] = lambda: providers.r2_client()
    r2_is_configured: Callable[[], bool] = lambda: providers.r2_is_configured()
    r2_bucket_name: str | Callable[[], str] = lambda: providers.R2_BUCKET_NAME
    record_r2_object: Callable[..., Any] = lambda *args, **kwargs: r2_ledger.record_object(*args, **kwargs)
    record_r2_deleted: Callable[[str], Any] = lambda key: r2_ledger.record_deleted(key)

    @classmethod
    def unconfigured(cls) -> "WorkerWebRuntime":
        """Canonical provider/config defaults with legacy-only callbacks closed."""

        return cls(
            cleanup_budget_state=_missing("cleanup_budget_state"),
            enforce_large_upload_budget=_missing("enforce_large_upload_budget"),
            release_reservation=_missing("release_reservation"),
            budget_status=_missing("budget_status"),
            download_staging=_missing("download_staging"),
            delete_staging=_missing("delete_staging"),
            commit_result=_missing("commit_result"),
            sync_media_processing_metadata=_missing("sync_media_processing_metadata"),
            worker_token=lambda: os.environ.get("MATERIAL_WORKER_TOKEN", "").strip(),
            direct_upload_enabled=lambda: _env_true("MATERIAL_DIRECT_UPLOAD_ENABLED", False),
            direct_upload_max_mb=lambda: _env_int("MATERIAL_DIRECT_UPLOAD_MAX_MB", 2048, 1, 4096),
            worker_url_ttl_seconds=lambda: _env_int("MATERIAL_WORKER_URL_TTL_SECONDS", 900, 60, 3600),
            max_attempts=lambda: _env_int("MATERIAL_JOB_MAX_ATTEMPTS", 3, 1, 8),
        )


def build_canonical_runtime(*, paths_provider=storage_paths) -> WorkerWebRuntime:
    """Compose all production worker-Web dependencies from canonical owners."""
    staging = MaterialStagingRuntime(paths_provider)

    def cleanup_staging() -> None:
        operations.cleanup_staging(staging.delete)

    return WorkerWebRuntime(
        cleanup_budget_state=lambda: r2_budget.cleanup_budget_state(
            cleanup_staging=cleanup_staging
        ),
        enforce_large_upload_budget=lambda upload_id, object_key, source_bytes: (
            r2_budget.enforce_large_upload_budget(
                upload_id,
                object_key,
                source_bytes,
                cleanup_staging=cleanup_staging,
            )
        ),
        release_reservation=r2_budget.release_reservation,
        budget_status=r2_budget.status,
        download_staging=staging.download,
        delete_staging=staging.delete,
        commit_result=job_commit.commit,
        sync_media_processing_metadata=media_metadata.sync,
        connection_factory=None,
        worker_token=lambda: os.environ.get("MATERIAL_WORKER_TOKEN", "").strip(),
        direct_upload_enabled=lambda: _env_true("MATERIAL_DIRECT_UPLOAD_ENABLED", False),
        direct_upload_max_mb=lambda: _env_int("MATERIAL_DIRECT_UPLOAD_MAX_MB", 2048, 1, 4096),
        worker_url_ttl_seconds=lambda: _env_int(
            "MATERIAL_WORKER_URL_TTL_SECONDS", 900, 60, 3600
        ),
        max_attempts=lambda: _env_int("MATERIAL_JOB_MAX_ATTEMPTS", 3, 1, 8),
    )


def runtime_from_owner(owner) -> WorkerWebRuntime:
    """Adapt a Base-shaped compatibility fixture at registration only."""

    return WorkerWebRuntime(
        cleanup_budget_state=lambda: getattr(owner, "cleanup_r2_budget_state", _missing("cleanup_budget_state"))(),
        enforce_large_upload_budget=lambda *args: getattr(owner, "enforce_r2_large_upload_budget", _missing("enforce_large_upload_budget"))(*args),
        release_reservation=lambda *args: getattr(owner, "_r2_release_reservation", _missing("release_reservation"))(*args),
        budget_status=lambda: getattr(owner, "r2_budget_status", _missing("budget_status"))(),
        download_staging=lambda *args: getattr(owner, "download_material_job_staging", _missing("download_staging"))(*args),
        delete_staging=lambda *args: getattr(owner, "delete_material_job_staging", _missing("delete_staging"))(*args),
        commit_result=lambda *args: getattr(owner, "commit_material_job_result", _missing("commit_result"))(*args),
        sync_media_processing_metadata=lambda *args: getattr(owner, "sync_media_processing_metadata", _missing("sync_media_processing_metadata"))(*args),
        connection_factory=(lambda: owner._db_conn()) if callable(getattr(owner, "_db_conn", None)) else None,
        worker_token=lambda: str(getattr(owner, "MATERIAL_WORKER_TOKEN", "") or ""),
        direct_upload_enabled=lambda: bool(getattr(owner, "MATERIAL_DIRECT_UPLOAD_ENABLED", _env_true("MATERIAL_DIRECT_UPLOAD_ENABLED", False))),
        direct_upload_max_mb=lambda: max(1, min(4096, int(getattr(owner, "MATERIAL_DIRECT_UPLOAD_MAX_MB", _env_int("MATERIAL_DIRECT_UPLOAD_MAX_MB", 2048, 1, 4096)) or 2048))),
        worker_url_ttl_seconds=lambda: max(60, min(3600, int(getattr(owner, "MATERIAL_WORKER_URL_TTL_SECONDS", _env_int("MATERIAL_WORKER_URL_TTL_SECONDS", 900, 60, 3600)) or 900))),
        max_attempts=lambda: max(1, min(8, int(getattr(owner, "MATERIAL_JOB_MAX_ATTEMPTS", _env_int("MATERIAL_JOB_MAX_ATTEMPTS", 3, 1, 8)) or 3))),
        r2_client_factory=lambda: getattr(owner, "r2_client", providers.r2_client)(),
        r2_is_configured=lambda: bool(getattr(owner, "r2_is_configured", providers.r2_is_configured)()),
        r2_bucket_name=lambda: str(getattr(owner, "R2_BUCKET_NAME", providers.R2_BUCKET_NAME) or ""),
        record_r2_object=lambda *args, **kwargs: getattr(owner, "r2_record_object", r2_ledger.record_object)(*args, **kwargs),
        record_r2_deleted=lambda *args: getattr(owner, "r2_record_deleted", r2_ledger.record_deleted)(*args),
    )


__all__ = ["WorkerWebRuntime", "build_canonical_runtime", "runtime_from_owner"]
