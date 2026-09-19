"""Canonical read-only media-processing metadata mirror.

``material_jobs`` remains the only queue/ownership state machine.  Migration
0067 owns ``media_processing_jobs``; this module merely mirrors status for media
reporting and deliberately treats a missing optional table as non-fatal.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from teacher_app.common import db as common_db
from teacher_app.materials.repository import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sync(job: dict, status: str, failure_reason: str = "") -> None:
    payload = dict(job.get("payload") or {})
    original = str(job.get("originalName") or payload.get("originalName") or "")
    if Path(original).suffix.lower() not in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS:
        return
    job_id = str(job.get("id") or "")
    material_id = str(job.get("materialId") or payload.get("materialId") or "")
    if not job_id or not material_id:
        return
    now = _now()
    conn, kind = common_db.get_connection()
    try:
        if kind == "postgres":
            conn.execute(
                "INSERT INTO media_processing_jobs("
                "id,material_id,material_job_id,status,failure_reason,created_at,updated_at"
                ") VALUES(%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT(id) DO UPDATE SET "
                "status=EXCLUDED.status,failure_reason=EXCLUDED.failure_reason,updated_at=EXCLUDED.updated_at",
                (job_id, material_id, job_id, status, failure_reason[:1200], now, now),
            )
        else:
            conn.execute(
                "INSERT INTO media_processing_jobs("
                "id,material_id,material_job_id,status,failure_reason,created_at,updated_at"
                ") VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "status=excluded.status,failure_reason=excluded.failure_reason,updated_at=excluded.updated_at",
                (job_id, material_id, job_id, status, failure_reason[:1200], now, now),
            )
    except Exception:
        # Reporting metadata must never alter queue correctness.
        pass
    finally:
        conn.close()


__all__ = ["sync"]
