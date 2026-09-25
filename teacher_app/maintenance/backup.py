"""Canonical logical backup/restore implementation.

HTTP/auth/elevation compatibility remains in root ``backup_restore.py`` while
archive validation and persistence ownership live here.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import io
import json
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from teacher_app.common import db as common_db
from teacher_app.common.auth import normalize_roles

BACKUP_FORMAT = "teacher-backup-v1"
DEFAULT_TABLES = (
    "user_accounts", "courses", "quiz_categories", "quiz_questions",
    "exam_records", "materials", "material_progress", "learning_assignments",
    "material_versions", "pgy_assignments", "pgy_assignment_audit",
    "exam_attempts", "schema_migrations", "learning_progress",
    "material_text_index", "media_processing_jobs", "atlas_import_previews",
    "audit_events", "external_media", "question_versions",
    "question_attempt_analytics",
)


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def app_version() -> str:
    try:
        value = Path(__file__).resolve().parents[2].joinpath("VERSION").read_text(encoding="utf-8").strip()
        return value or "unknown"
    except Exception:
        return "unknown"


@contextmanager
def _read_scope(connection_factory: Callable | None = None):
    if connection_factory is None:
        with common_db.read_connection() as pair:
            yield pair
        return
    conn, kind = connection_factory()
    try:
        yield conn, kind
    finally:
        conn.close()


@contextmanager
def _write_scope(connection_factory: Callable | None = None):
    if connection_factory is None:
        with common_db.transaction() as pair:
            yield pair
        return
    conn, kind = connection_factory()
    try:
        if kind == "postgres" and hasattr(conn, "transaction"):
            with conn.transaction():
                yield conn, kind
        else:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn, kind
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()
    finally:
        conn.close()


def _existing_tables(conn, kind: str) -> set[str]:
    if kind == "postgres":
        rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()
        return {str(dict(row).get("tablename", "")) for row in rows}
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(dict(row).get("name", "")) for row in rows}


def _table_rows(conn, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(f'SELECT * FROM "{table}"').fetchall()]


def _table_columns(conn, kind: str, table: str) -> set[str]:
    if kind == "postgres":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s",
            (table,),
        ).fetchall()
        return {str(dict(row).get("column_name", "")) for row in rows}
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {str(row[1]) for row in rows}


def compatible_restore_row(table: str, row: dict[str, Any], destination_columns: set[str]) -> dict[str, Any]:
    compatible = {column: value for column, value in row.items() if column in destination_columns}
    if table == "user_accounts" and "roles_json" in destination_columns and "roles_json" not in compatible:
        compatible["roles_json"] = json.dumps(
            normalize_roles(None, primary=row.get("role")),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return compatible


def build_backup(connection_factory: Callable | None = None) -> dict[str, Any]:
    with _read_scope(connection_factory) as (conn, kind):
        existing = _existing_tables(conn, kind)
        tables = {name: _table_rows(conn, name) for name in DEFAULT_TABLES if name in existing}
    payload = {
        "format": BACKUP_FORMAT,
        "createdAt": utcnow(),
        "version": app_version(),
        "tables": tables,
    }
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    payload["sha256"] = hashlib.sha256(body).hexdigest()
    return payload


def zip_payload(payload: dict[str, Any]) -> bytes:
    raw = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("teacher-backup.json", raw)
    return buf.getvalue()


def parse_backup_zip(raw: bytes, *, max_expanded_mb: int = 500) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if names != ["teacher-backup.json"]:
            raise ValueError("備份 ZIP 結構不正確。")
        info = archive.getinfo(names[0])
        max_expanded = max(1, min(2048, int(max_expanded_mb))) * 1024 * 1024
        if info.file_size > max_expanded:
            raise ValueError("備份解壓後大小超過限制。")
        payload = json.loads(archive.read(names[0]).decode("utf-8"))

    if payload.get("format") != BACKUP_FORMAT or not isinstance(payload.get("tables"), dict):
        raise ValueError("不是 Teacher 備份格式。")
    stored_sha = str(payload.get("sha256") or "").strip().lower()
    unsigned = dict(payload)
    unsigned.pop("sha256", None)
    expected_sha = hashlib.sha256(
        json.dumps(unsigned, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    if not stored_sha or not hmac.compare_digest(stored_sha, expected_sha):
        raise ValueError("備份 SHA256 驗證失敗。")
    return payload


def restore_backup(payload: dict[str, Any], connection_factory: Callable | None = None) -> dict[str, int]:
    restored: dict[str, int] = {}
    with _write_scope(connection_factory) as (conn, kind):
        ph = common_db.placeholder(kind)
        existing = _existing_tables(conn, kind)
        for table, rows in payload.get("tables", {}).items():
            if table not in DEFAULT_TABLES or table not in existing or not isinstance(rows, list):
                continue
            destination_columns = _table_columns(conn, kind, table)
            count = 0
            for row in rows:
                if not isinstance(row, dict) or not row:
                    continue
                compatible = compatible_restore_row(table, row, destination_columns)
                if not compatible:
                    continue
                cols = list(compatible)
                placeholders = ",".join([ph] * len(cols))
                col_sql = ",".join(f'"{column}"' for column in cols)
                values = tuple(compatible[column] for column in cols)
                try:
                    if kind == "postgres":
                        result = conn.execute(
                            f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING',
                            values,
                        )
                    else:
                        result = conn.execute(
                            f'INSERT OR IGNORE INTO "{table}" ({col_sql}) VALUES ({placeholders})',
                            values,
                        )
                    count += max(0, int(result.rowcount or 0))
                except Exception:
                    # Restore stays conservative: incompatible individual rows are skipped.
                    continue
            restored[table] = count
    return restored
