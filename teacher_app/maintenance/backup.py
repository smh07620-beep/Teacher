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
    "exam_records", "materials", "pgy_assignments", "pgy_assignment_audit",
    "exam_attempts", "schema_migrations", "learning_progress",
    "material_text_index", "media_processing_jobs", "atlas_import_previews",
    "audit_events", "external_media", "question_versions",
    "question_attempt_analytics", "media_script_jobs", "media_scripts",
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


def _json_ready(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _json_restore(value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {"__bytes__"}:
        return bytes.fromhex(str(value["__bytes__"]))
    if isinstance(value, dict):
        return {key: _json_restore(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_restore(item) for item in value]
    return value


def create_backup_payload(connection_factory: Callable | None = None) -> dict[str, Any]:
    with _read_scope(connection_factory) as (conn, kind):
        existing = _existing_tables(conn, kind)
        tables = {
            table: [_json_ready(row) for row in _table_rows(conn, table)]
            for table in DEFAULT_TABLES
            if table in existing
        }
    return {
        "format": BACKUP_FORMAT,
        "createdAt": utcnow(),
        "appVersion": app_version(),
        "tables": tables,
    }


def canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sign_payload(payload: dict[str, Any], signing_key: str) -> str:
    return hmac.new(
        signing_key.encode("utf-8"),
        canonical_json(payload),
        hashlib.sha256,
    ).hexdigest()


def create_archive(payload: dict[str, Any], signing_key: str) -> bytes:
    signature = sign_payload(payload, signing_key)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("backup.json", canonical_json(payload))
        archive.writestr("backup.sig", signature)
    return buffer.getvalue()


def read_archive(blob: bytes, signing_key: str) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(blob), "r") as archive:
            names = set(archive.namelist())
            if names != {"backup.json", "backup.sig"}:
                raise ValueError("備份封裝格式不正確。")
            raw = archive.read("backup.json")
            signature = archive.read("backup.sig").decode("utf-8").strip()
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
        raise ValueError("備份檔案損壞或格式不正確。") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("備份內容不是有效 JSON。") from exc
    if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT:
        raise ValueError("不支援的備份格式。")
    expected = sign_payload(payload, signing_key)
    if not hmac.compare_digest(signature, expected):
        raise ValueError("備份簽章驗證失敗。")
    return payload


def _table_columns(conn, kind: str, table: str) -> list[str]:
    if kind == "postgres":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
            (table,),
        ).fetchall()
        return [str(dict(row).get("column_name", "")) for row in rows]
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [str(dict(row).get("name", "")) for row in rows]


def _restore_table(conn, kind: str, table: str, rows: list[dict[str, Any]]) -> None:
    columns = _table_columns(conn, kind, table)
    if not columns:
        return
    conn.execute(f'DELETE FROM "{table}"')
    if not rows:
        return
    ph = common_db.placeholder(kind)
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            raise ValueError(f"備份表 {table} 的資料列格式不正確。")
        row = {key: _json_restore(value) for key, value in raw_row.items() if key in columns}
        keys = [column for column in columns if column in row]
        if not keys:
            continue
        quoted = ",".join(f'"{key}"' for key in keys)
        values = ",".join(ph for _ in keys)
        params = [row[key] for key in keys]
        conn.execute(f'INSERT INTO "{table}" ({quoted}) VALUES ({values})', params)


def restore_backup_payload(payload: dict[str, Any], connection_factory: Callable | None = None) -> dict[str, int]:
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("備份內容缺少 tables。")
    unknown = set(tables) - set(DEFAULT_TABLES)
    if unknown:
        raise ValueError("備份包含不允許還原的資料表：" + ", ".join(sorted(unknown)))

    with _write_scope(connection_factory) as (conn, kind):
        existing = _existing_tables(conn, kind)
        restored: dict[str, int] = {}
        for table in DEFAULT_TABLES:
            if table not in tables or table not in existing:
                continue
            rows = tables.get(table)
            if not isinstance(rows, list):
                raise ValueError(f"備份表 {table} 格式不正確。")
            _restore_table(conn, kind, table, rows)
            restored[table] = len(rows)
    return restored


def backup_filename() -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"teacher-backup-{stamp}.zip"


__all__ = [
    "BACKUP_FORMAT",
    "DEFAULT_TABLES",
    "backup_filename",
    "create_archive",
    "create_backup_payload",
    "read_archive",
    "restore_backup_payload",
    "sign_payload",
]
