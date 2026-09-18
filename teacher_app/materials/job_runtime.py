"""Narrow runtime seam for material-job HTTP orchestration.

Queue persistence belongs to :mod:`teacher_app.worker.repository`.  This seam
contains only Web-runtime operations that have not yet been extracted from the
legacy host: shared staging, progress files, R2 budget/operations reporting,
and media-processing metadata mirroring.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from teacher_app.config import storage_paths
from teacher_app.materials.staging_runtime import MaterialStagingRuntime
from teacher_app.materials.upload_progress import UploadProgressStore
from teacher_app.storage import r2_budget
from teacher_app.worker import media_metadata, operations


ConnectionFactory = Callable[[], tuple[Any, str]]


@dataclass(frozen=True)
class MaterialJobRuntime:
    upload_staging: Callable[[Path, str, str], tuple[str, str, str]]
    staging_exists: Callable[[dict], bool]
    delete_staging: Callable[[dict], None]
    cleanup_budget_state: Callable[[], None]
    operations_status: Callable[[], dict]
    staging_capability: Callable[[], dict]
    progress_path: Callable[[str], Path]
    clear_progress: Callable[[str], None]
    set_progress: Callable[[str, float, str, str], None]
    sync_media_processing_metadata: Callable[[dict, str], None]
    connection_factory: ConnectionFactory | None = None
    background_enabled: bool | Callable[[], bool] = True
    worker_enabled: bool | Callable[[], bool] = True
    max_attempts: int | Callable[[], int] = 3


def _env_true(name: str, default: bool) -> bool:
    fallback = "true" if default else "false"
    return os.environ.get(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


def _max_attempts() -> int:
    try:
        value = int(os.environ.get("MATERIAL_JOB_MAX_ATTEMPTS", "3"))
    except ValueError:
        value = 3
    return max(1, min(8, value))


def build_canonical_runtime(*, paths_provider=storage_paths) -> MaterialJobRuntime:
    """Compose the Web material-job runtime without a compatibility namespace."""
    staging = MaterialStagingRuntime(paths_provider)

    def progress_store() -> UploadProgressStore:
        return UploadProgressStore(paths_provider())

    def cleanup_staging() -> None:
        operations.cleanup_staging(staging.delete)

    return MaterialJobRuntime(
        upload_staging=staging.upload,
        staging_exists=staging.exists,
        delete_staging=staging.delete,
        cleanup_budget_state=lambda: r2_budget.cleanup_budget_state(
            cleanup_staging=cleanup_staging
        ),
        operations_status=lambda: operations.status(staging.capability),
        staging_capability=staging.capability,
        progress_path=lambda progress_id: progress_store().path(progress_id),
        clear_progress=lambda progress_id: progress_store().clear(progress_id),
        set_progress=lambda *args, **kwargs: progress_store().set(*args, **kwargs),
        sync_media_processing_metadata=media_metadata.sync,
        connection_factory=None,
        background_enabled=lambda: _env_true("MATERIAL_BACKGROUND_JOBS", True),
        worker_enabled=lambda: _env_true("MATERIAL_WORKER_ENABLED", True),
        max_attempts=_max_attempts,
    )


def from_compat_owner(owner) -> MaterialJobRuntime:
    """Adapt a legacy/isolated owner without teaching routes its broad shape."""
    return MaterialJobRuntime(
        upload_staging=lambda *args: owner.upload_material_job_staging(*args),
        staging_exists=lambda job: owner.material_job_staging_exists(job),
        delete_staging=lambda job: owner.delete_material_job_staging(job),
        cleanup_budget_state=lambda: owner.cleanup_r2_budget_state(),
        operations_status=lambda: owner.material_job_operations_status(),
        staging_capability=lambda: owner.shared_staging_capability(),
        progress_path=lambda progress_id: owner._upload_progress_path(progress_id),
        clear_progress=lambda progress_id: owner.clear_upload_progress(progress_id),
        set_progress=lambda *args: owner.set_upload_progress(*args),
        sync_media_processing_metadata=lambda *args: owner.sync_media_processing_metadata(*args),
        connection_factory=(lambda: owner._db_conn()) if callable(getattr(owner, "_db_conn", None)) else None,
        background_enabled=lambda: bool(
            getattr(owner, "MATERIAL_BACKGROUND_JOBS", _env_true("MATERIAL_BACKGROUND_JOBS", True))
        ),
        worker_enabled=lambda: bool(
            getattr(owner, "MATERIAL_WORKER_ENABLED", _env_true("MATERIAL_WORKER_ENABLED", True))
        ),
        max_attempts=lambda: max(
            1,
            min(8, int(getattr(owner, "MATERIAL_JOB_MAX_ATTEMPTS", _max_attempts()) or 3)),
        ),
    )


__all__ = ["MaterialJobRuntime", "build_canonical_runtime", "from_compat_owner"]
