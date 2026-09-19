"""Canonical R2 free-tier reservation and budget policy.

Migration 0067 owns the tables.  This module owns runtime accounting policy and
never creates/changes schema.  Keeping reservation SQL here avoids copying it
into HTTP/worker runtimes while preserving the transaction/lock semantics of
the historical host.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
from dataclasses import dataclass
from typing import Callable

from teacher_app.common import db as common_db
from teacher_app.storage import providers
from teacher_app.worker import repository as worker_repository


_GB = 1024**3


def _bounded_number(name: str, default, minimum, maximum, caster=float):
    try:
        value = caster(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = caster(default)
    return max(caster(minimum), min(caster(maximum), value))


def _env_true(name: str, default: bool) -> bool:
    fallback = "true" if default else "false"
    return os.environ.get(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class R2BudgetPolicy:
    free_only: bool
    free_storage_gb_month: float
    warning_percent: int
    upload_block_percent: int
    emergency_percent: int
    staging_max_current_gb: float
    failed_retention_hours: int
    multipart_abandon_hours: int
    large_file_mb: int

    @classmethod
    def from_env(cls) -> "R2BudgetPolicy":
        warning = int(_bounded_number("R2_WARNING_PERCENT", 60, 1, 99, int))
        blocked = int(_bounded_number("R2_UPLOAD_BLOCK_PERCENT", 80, warning, 99, int))
        emergency = int(_bounded_number("R2_EMERGENCY_PERCENT", 90, blocked, 100, int))
        return cls(
            free_only=_env_true("FREE_ONLY_MODE", True),
            free_storage_gb_month=float(
                _bounded_number("R2_FREE_STORAGE_GB_MONTH", 10.0, 0.1, 10000.0)
            ),
            warning_percent=warning,
            upload_block_percent=blocked,
            emergency_percent=emergency,
            staging_max_current_gb=float(
                _bounded_number("R2_STAGING_MAX_CURRENT_GB", 8.0, 0.1, 1000.0)
            ),
            failed_retention_hours=int(
                _bounded_number("R2_STAGING_FAILED_RETENTION_HOURS", 24, 1, 720, int)
            ),
            multipart_abandon_hours=int(
                _bounded_number("R2_MULTIPART_ABANDON_HOURS", 6, 1, 168, int)
            ),
            large_file_mb=int(
                _bounded_number("MATERIAL_R2_LARGE_FILE_MB", 100, 1, 4096, int)
            ),
        )


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _parse_time(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def _month_bounds(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    now = now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return start, end


def _staging_totals(conn) -> tuple[int, int]:
    rows = conn.execute(
        "SELECT object_bytes FROM r2_usage_ledger WHERE is_staging=TRUE AND deleted_at=''"
    ).fetchall()
    staging = sum(max(0, int(dict(row).get("object_bytes") or 0)) for row in rows)
    rows = conn.execute(
        "SELECT reserved_bytes FROM r2_upload_reservations WHERE status='active'"
    ).fetchall()
    reserved = sum(max(0, int(dict(row).get("reserved_bytes") or 0)) for row in rows)
    return staging, reserved


def _estimated_gb_month(conn, now=None) -> float:
    """Teacher-owned estimate from the private ledger, never an R2 invoice."""
    now = now or dt.datetime.now(dt.timezone.utc)
    start, end = _month_bounds(now)
    total = 0.0
    for row in conn.execute(
        "SELECT object_bytes,uploaded_at,deleted_at FROM r2_usage_ledger"
    ).fetchall():
        item = dict(row)
        uploaded = _parse_time(item.get("uploaded_at"))
        deleted = _parse_time(item.get("deleted_at")) or now
        if not uploaded:
            continue
        active_start = max(uploaded, start)
        active_end = min(deleted, now, end)
        if active_end > active_start:
            total += (
                max(0, int(item.get("object_bytes") or 0))
                / _GB
                * ((active_end - active_start).total_seconds() / (end - start).total_seconds())
            )
    return total


def budget_level(percent: float, *, policy: R2BudgetPolicy | None = None) -> str:
    policy = policy or R2BudgetPolicy.from_env()
    if percent >= policy.emergency_percent:
        return "emergency"
    if percent >= policy.upload_block_percent:
        return "blocked"
    if percent >= policy.warning_percent:
        return "warning"
    return "green"


def large_file(source_bytes: int, *, policy: R2BudgetPolicy | None = None) -> bool:
    policy = policy or R2BudgetPolicy.from_env()
    return int(source_bytes or 0) >= policy.large_file_mb * 1024 * 1024


def release_reservation(upload_id: str, reason: str) -> None:
    conn, kind = common_db.get_connection()
    ph = "%s" if kind == "postgres" else "?"
    try:
        conn.execute(
            f"UPDATE r2_upload_reservations SET status='released', released_at={ph}, "
            f"release_reason={ph} WHERE upload_id={ph} AND status='active'",
            (_utc_now_iso(), str(reason)[:80], str(upload_id)),
        )
    finally:
        conn.close()


def _reserve_on_connection(
    conn,
    kind: str,
    *,
    upload_id: str,
    object_key: str,
    source_bytes: int,
    policy: R2BudgetPolicy,
    now: dt.datetime,
) -> None:
    staging, reserved = _staging_totals(conn)
    estimate = _estimated_gb_month(conn, now)
    start, end = _month_bounds(now)
    projected = estimate + source_bytes / _GB * (
        (end - now).total_seconds() / (end - start).total_seconds()
    )
    if (
        policy.free_only
        and projected / policy.free_storage_gb_month * 100 >= policy.upload_block_percent
    ):
        raise ValueError("R2 免費額度預估已達大型檔案上傳安全門檻。")
    if staging + reserved + source_bytes > policy.staging_max_current_gb * _GB:
        raise ValueError("R2 staging 已達 8GB 安全上限。")

    expiry = (now + dt.timedelta(hours=policy.multipart_abandon_hours)).isoformat()
    row_id = "r2res-" + hashlib.sha256(upload_id.encode()).hexdigest()[:24]
    if kind == "postgres":
        conn.execute(
            "INSERT INTO r2_upload_reservations("
            "id,upload_id,object_key,reserved_bytes,status,created_at,expires_at,released_at,release_reason"
            ") VALUES(%s,%s,%s,%s,'active',%s,%s,'','')",
            (row_id, upload_id, object_key, source_bytes, now.isoformat(), expiry),
        )
    else:
        conn.execute(
            "INSERT INTO r2_upload_reservations("
            "id,upload_id,object_key,reserved_bytes,status,created_at,expires_at,released_at,release_reason"
            ") VALUES(?,?,?,?,?,?,?,?,?)",
            (
                row_id,
                upload_id,
                object_key,
                source_bytes,
                "active",
                now.isoformat(),
                expiry,
                "",
                "",
            ),
        )


def reserve_upload(
    upload_id: str,
    object_key: str,
    source_bytes: int,
    *,
    policy: R2BudgetPolicy | None = None,
) -> None:
    """Atomically reserve staging capacity for one large/direct upload."""
    size = max(0, int(source_bytes or 0))
    if size <= 0:
        raise ValueError("上傳大小不合法。")
    upload_id = str(upload_id)
    policy = policy or R2BudgetPolicy.from_env()
    now = dt.datetime.now(dt.timezone.utc)
    conn, kind = common_db.get_connection()
    try:
        if kind == "postgres":
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(67002026)")
                _reserve_on_connection(
                    conn,
                    kind,
                    upload_id=upload_id,
                    object_key=str(object_key),
                    source_bytes=size,
                    policy=policy,
                    now=now,
                )
        else:
            conn.execute("BEGIN IMMEDIATE")
            try:
                _reserve_on_connection(
                    conn,
                    kind,
                    upload_id=upload_id,
                    object_key=str(object_key),
                    source_bytes=size,
                    policy=policy,
                    now=now,
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()


def status(*, policy: R2BudgetPolicy | None = None) -> dict:
    policy = policy or R2BudgetPolicy.from_env()
    conn, kind = common_db.get_connection()
    try:
        staging, reserved = _staging_totals(conn)
        estimate = _estimated_gb_month(conn)
        percent = (
            estimate / policy.free_storage_gb_month * 100
            if policy.free_storage_gb_month
            else 100.0
        )
        parts = conn.execute(
            "SELECT COALESCE(SUM(multipart_parts),0) AS count,"
            "COALESCE(SUM(estimated_operations),0) AS operations FROM r2_usage_ledger"
        ).fetchone()
        cleanup_pending = conn.execute(
            "SELECT COUNT(*) AS count FROM material_jobs WHERE cleanup_pending="
            + ("TRUE" if kind == "postgres" else "1")
        ).fetchone()
    finally:
        conn.close()

    try:
        upload_counts = worker_repository.upload_session_status_counts()
    except Exception:
        upload_counts = {}
    return {
        "enabled": bool(policy.free_only),
        "estimatedOnly": True,
        "freeStorageGbMonth": policy.free_storage_gb_month,
        "estimatedGbMonth": round(estimate, 6),
        "currentStagingBytes": staging,
        "reservedBytes": reserved,
        "usagePercent": round(percent, 2),
        "level": budget_level(percent, policy=policy),
        "activeUploads": int(upload_counts.get("uploading", 0) or 0),
        "cleanupPending": int(dict(cleanup_pending).get("count") or 0),
        "multipartParts": int(dict(parts).get("count") or 0),
        "estimatedOperations": int(dict(parts).get("operations") or 0),
    }


def cleanup_budget_state(
    *,
    cleanup_staging: Callable[[], None] | None = None,
    policy: R2BudgetPolicy | None = None,
) -> int:
    """Abort abandoned multipart uploads and release expired reservations."""
    policy = policy or R2BudgetPolicy.from_env()
    cutoff = (
        dt.datetime.now(dt.timezone.utc)
        - dt.timedelta(hours=policy.multipart_abandon_hours)
    ).isoformat()
    try:
        stale = worker_repository.list_stale_upload_sessions(cutoff)
    except Exception:
        stale = []
    expired = 0
    for item in stale:
        if str(item.get("status") or "") != "uploading":
            continue
        try:
            providers.r2_client().abort_multipart_upload(
                Bucket=providers.R2_BUCKET_NAME,
                Key=str(item.get("stagingKey") or item.get("staging_key") or ""),
                UploadId=str(item.get("r2UploadId") or item.get("r2_upload_id") or ""),
            )
        except Exception:
            # Remote upload can already be gone; local reservation/session still
            # must be released so capacity does not remain permanently blocked.
            pass
        try:
            worker_repository.cas_upload_session_status(
                str(item.get("id") or ""),
                expected_status="uploading",
                new_status="expired",
                updated_at=_utc_now_iso(),
            )
        except Exception:
            pass
        release_reservation(str(item.get("id") or ""), "multipart_expired")
        expired += 1

    now = _utc_now_iso()
    conn, kind = common_db.get_connection()
    ph = "%s" if kind == "postgres" else "?"
    try:
        conn.execute(
            f"UPDATE r2_upload_reservations SET status='released', released_at={ph}, "
            f"release_reason='reservation_expired' WHERE status='active' AND expires_at < {ph}",
            (now, now),
        )
    finally:
        conn.close()
    if cleanup_staging is not None:
        cleanup_staging()
    return expired


def enforce_large_upload_budget(
    upload_id: str,
    object_key: str,
    source_bytes: int,
    *,
    cleanup_staging: Callable[[], None] | None = None,
    policy: R2BudgetPolicy | None = None,
) -> None:
    policy = policy or R2BudgetPolicy.from_env()
    if not large_file(source_bytes, policy=policy):
        return
    cleanup_budget_state(cleanup_staging=cleanup_staging, policy=policy)
    current = status(policy=policy)
    if policy.free_only and current["level"] == "emergency":
        raise ValueError("R2 免費額度進入緊急保護，暫停大型檔案上傳。")
    if policy.free_only and current["level"] == "blocked":
        raise ValueError("R2 免費額度預估已達大型檔案上傳安全門檻。")
    reserve_upload(upload_id, object_key, source_bytes, policy=policy)


__all__ = [
    "R2BudgetPolicy",
    "budget_level",
    "cleanup_budget_state",
    "enforce_large_upload_budget",
    "large_file",
    "release_reservation",
    "reserve_upload",
    "status",
]
