"""Canonical persistence owner for Cloudflare R2 usage observations.

Schema ownership remains in release migration 0067.  This module intentionally
contains no DDL and only records/deletes observations against that migrated
schema, using the shared process-local database connection seam.
"""
from __future__ import annotations

import datetime as dt
import hashlib

from teacher_app.common import db as common_db


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def record_object(
    object_key: str,
    object_bytes: int,
    *,
    multipart_parts=0,
    estimated_operations=1,
    is_staging=None,
) -> None:
    """Upsert one live R2 object into the private usage ledger."""
    if not object_key:
        return
    key = str(object_key)[:1024]
    size = max(0, int(object_bytes or 0))
    staging = (
        bool(key.startswith("_staging/"))
        if is_staging is None
        else bool(is_staging)
    )
    now = _utc_now_iso()
    conn, kind = common_db.get_connection()
    try:
        row_id = "r2obj-" + hashlib.sha256(key.encode()).hexdigest()[:24]
        parts = int(multipart_parts or 0)
        operations = max(1, int(estimated_operations or 1))
        if kind == "postgres":
            conn.execute(
                "INSERT INTO r2_usage_ledger("
                "id,object_key,object_bytes,uploaded_at,deleted_at,multipart_parts,estimated_operations,is_staging"
                ") VALUES(%s,%s,%s,%s,'',%s,%s,%s) "
                "ON CONFLICT(object_key) DO UPDATE SET "
                "object_bytes=EXCLUDED.object_bytes,uploaded_at=EXCLUDED.uploaded_at,deleted_at='',"
                "multipart_parts=EXCLUDED.multipart_parts,"
                "estimated_operations=r2_usage_ledger.estimated_operations + EXCLUDED.estimated_operations,"
                "is_staging=EXCLUDED.is_staging",
                (row_id, key, size, now, parts, operations, staging),
            )
        else:
            conn.execute(
                "INSERT INTO r2_usage_ledger("
                "id,object_key,object_bytes,uploaded_at,deleted_at,multipart_parts,estimated_operations,is_staging"
                ") VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(object_key) DO UPDATE SET "
                "object_bytes=excluded.object_bytes,uploaded_at=excluded.uploaded_at,deleted_at='',"
                "multipart_parts=excluded.multipart_parts,"
                "estimated_operations=r2_usage_ledger.estimated_operations + excluded.estimated_operations,"
                "is_staging=excluded.is_staging",
                (row_id, key, size, now, "", parts, operations, int(staging)),
            )
    finally:
        conn.close()


def record_deleted(object_key: str) -> None:
    """Mark one live object deleted and account for the delete operation."""
    if not object_key:
        return
    conn, kind = common_db.get_connection()
    placeholder = "%s" if kind == "postgres" else "?"
    try:
        conn.execute(
            f"UPDATE r2_usage_ledger SET deleted_at={placeholder}, "
            f"estimated_operations=estimated_operations+1 "
            f"WHERE object_key={placeholder} AND deleted_at=''",
            (_utc_now_iso(), str(object_key)[:1024]),
        )
    finally:
        conn.close()


__all__ = ["record_deleted", "record_object"]
