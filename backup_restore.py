"""Teacher 6.4 logical backup and restore endpoints.

Backups are JSON snapshots of application tables plus a material manifest. They
are intended to complement, not replace, provider-level PostgreSQL/storage
backups. Restore is restricted to education/system administrators and requires
an explicit confirmation token.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any

from flask import jsonify, request, send_file

BACKUP_FORMAT = "teacher-backup-v1"
DEFAULT_TABLES = (
    "user_accounts", "courses", "quiz_categories", "quiz_questions",
    "exam_records", "materials", "pgy_assignments", "pgy_assignment_audit",
    "exam_attempts", "schema_migrations",
)


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def app_version() -> str:
    try:
        value = (
            Path(__file__)
            .with_name("VERSION")
            .read_text(encoding="utf-8")
            .strip()
        )
        return value or "unknown"
    except Exception:
        return "unknown"


def _role(base, user) -> str:
    return base.normalize_role((user or {}).get("role", "student"))


def _auth(base, allowed):
    user = base._current_user()
    if not user:
        return None, (jsonify({"error": "請先登入。"}), 401)
    if _role(base, user) not in {base.normalize_role(r) for r in allowed}:
        return None, (jsonify({"error": "權限不足。"}), 403)
    return user, None


def _existing_tables(conn, kind: str) -> set[str]:
    if kind == "postgres":
        rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()
        return {str(dict(r).get("tablename", "")) for r in rows}
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(dict(r).get("name", "")) for r in rows}


def _table_rows(conn, table: str) -> list[dict[str, Any]]:
    rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
    return [dict(r) for r in rows]


def build_backup(base) -> dict[str, Any]:
    conn, kind = base._db_conn()
    try:
        existing = _existing_tables(conn, kind)
        tables = {name: _table_rows(conn, name) for name in DEFAULT_TABLES if name in existing}
    finally:
        conn.close()
    payload = {
        "format": BACKUP_FORMAT,
        "createdAt": utcnow(),
        "version": app_version(),
        "tables": tables,
    }
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    payload["sha256"] = hashlib.sha256(body).hexdigest()
    return payload


def _zip_payload(payload: dict[str, Any]) -> bytes:
    raw = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("teacher-backup.json", raw)
    return buf.getvalue()


def _read_backup_upload() -> dict[str, Any]:
    f = request.files.get("file")
    if not f:
        raise ValueError("請上傳備份 ZIP。")
    max_mb = max(1, min(500, int(os.environ.get("BACKUP_MAX_UPLOAD_MB", "100"))))
    raw = f.read(max_mb * 1024 * 1024 + 1)
    if len(raw) > max_mb * 1024 * 1024:
        raise ValueError("備份檔超過允許大小。")
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
        if names != ["teacher-backup.json"]:
            raise ValueError("備份 ZIP 結構不正確。")
        info = zf.getinfo(names[0])
        max_expanded = max(1, min(2048, int(os.environ.get("BACKUP_MAX_EXPANDED_MB", "500")))) * 1024 * 1024
        if info.file_size > max_expanded:
            raise ValueError("備份解壓後大小超過限制。")
        payload = json.loads(zf.read(names[0]).decode("utf-8"))
    if payload.get("format") != BACKUP_FORMAT or not isinstance(payload.get("tables"), dict):
        raise ValueError("不是 Teacher 備份格式。")

    stored_sha = str(payload.get("sha256") or "").strip().lower()

    unsigned = dict(payload)
    unsigned.pop("sha256", None)

    unsigned_raw = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")

    expected_sha = hashlib.sha256(unsigned_raw).hexdigest()

    if not stored_sha or not hmac.compare_digest(
        stored_sha,
        expected_sha,
    ):
        raise ValueError("備份 SHA256 驗證失敗。")

    return payload


def _restore(base, payload: dict[str, Any]) -> dict[str, int]:
    conn, kind = base._db_conn()
    ph = "%s" if kind == "postgres" else "?"
    restored: dict[str, int] = {}
    try:
        existing = _existing_tables(conn, kind)
        for table, rows in payload.get("tables", {}).items():
            if table not in DEFAULT_TABLES or table not in existing or not isinstance(rows, list):
                continue
            # Conservative restore: insert missing primary-key rows only. It never
            # truncates or overwrites live production data.
            count = 0
            for row in rows:
                if not isinstance(row, dict) or not row:
                    continue
                cols = list(row.keys())
                placeholders = ",".join([ph] * len(cols))
                col_sql = ",".join(f'"{c}"' for c in cols)
                values = tuple(row[c] for c in cols)
                try:
                    if kind == "postgres":
                        conn.execute(f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING', values)
                    else:
                        conn.execute(f'INSERT OR IGNORE INTO "{table}" ({col_sql}) VALUES ({placeholders})', values)
                    count += 1
                except Exception:
                    continue
            restored[table] = count
    finally:
        conn.close()
    return restored


def register_backup_restore(base):
    app = base.app
    if app.extensions.get("teacher_backup_restore_registered"):
        return app
    app.extensions["teacher_backup_restore_registered"] = True

    @app.get("/api/maintenance/backup")
    def teacher_backup_download():
        user, denied = _auth(base, {"education_admin", "system_admin"})
        if denied:
            return denied
        payload = build_backup(base)
        data = _zip_payload(payload)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        return send_file(io.BytesIO(data), mimetype="application/zip", as_attachment=True,
                         download_name=f"teacher-backup-{stamp}.zip")

    @app.post("/api/maintenance/restore")
    def teacher_backup_restore():
        user, denied = _auth(base, {"education_admin", "system_admin"})
        if denied:
            return denied
        if str(request.form.get("confirm", "")) != "RESTORE":
            return jsonify({"error": "還原前請輸入 RESTORE 確認。"}), 400
        try:
            payload = _read_backup_upload()
            restored = _restore(base, payload)
            return jsonify({"ok": True, "restored": restored, "backupCreatedAt": payload.get("createdAt", "")})
        except Exception as exc:
            return jsonify({"error": str(exc)[:500]}), 400

    return app
