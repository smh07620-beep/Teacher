"""Canonical document-template persistence and content validation.

Provider transports stay outside this module.  HTTP adapters inject the
currently selected storage runtime so this module can own durable metadata and
file validation without constructing cloud clients or reading credentials.
"""
from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from teacher_app.common import db as common_db


DOC_TEMPLATE_ALLOWED_EXT = frozenset({".docx"})


def init_schema(connection_factory=None) -> None:
    if connection_factory is None:
        with common_db.transaction() as (conn, kind):
            _create_schema(conn, kind)
        return
    conn, kind = connection_factory()
    try:
        _create_schema(conn, kind)
    finally:
        conn.close()


def _create_schema(conn, kind: str) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS doc_templates (
            group_key TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            storage_filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            storage_backend TEXT NOT NULL DEFAULT 'local',
            storage_key TEXT NOT NULL DEFAULT ''
        )
        """
    )
    if kind == "postgres":
        conn.execute(
            "ALTER TABLE doc_templates ADD COLUMN IF NOT EXISTS storage_backend TEXT NOT NULL DEFAULT 'local'"
        )
        conn.execute(
            "ALTER TABLE doc_templates ADD COLUMN IF NOT EXISTS storage_key TEXT NOT NULL DEFAULT ''"
        )
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(doc_templates)").fetchall()}
    if "storage_backend" not in columns:
        conn.execute("ALTER TABLE doc_templates ADD COLUMN storage_backend TEXT NOT NULL DEFAULT 'local'")
    if "storage_key" not in columns:
        conn.execute("ALTER TABLE doc_templates ADD COLUMN storage_key TEXT NOT NULL DEFAULT ''")


def list_templates() -> dict[str, dict]:
    with common_db.read_connection() as (conn, _kind):
        rows = conn.execute("SELECT * FROM doc_templates").fetchall()
    return {row["group_key"]: dict(row) for row in rows}


def get_template(group_key: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM doc_templates WHERE group_key = {ph}",
            (group_key,),
        ).fetchone()
    return dict(row) if row else None


def save_template(
    group_key: str,
    filename: str,
    storage_filename: str,
    storage_backend: str = "local",
    storage_key: str = "",
) -> None:
    uploaded_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    backend = str(storage_backend or "local").lower()
    key = str(storage_key or "")
    with common_db.transaction() as (conn, kind):
        values = (group_key, filename, storage_filename, uploaded_at, backend, key)
        if kind == "postgres":
            conn.execute(
                """
                INSERT INTO doc_templates
                    (group_key, filename, storage_filename, uploaded_at, storage_backend, storage_key)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (group_key) DO UPDATE SET
                    filename=EXCLUDED.filename,
                    storage_filename=EXCLUDED.storage_filename,
                    uploaded_at=EXCLUDED.uploaded_at,
                    storage_backend=EXCLUDED.storage_backend,
                    storage_key=EXCLUDED.storage_key
                """,
                values,
            )
        else:
            conn.execute(
                """
                INSERT INTO doc_templates
                    (group_key, filename, storage_filename, uploaded_at, storage_backend, storage_key)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(group_key) DO UPDATE SET
                    filename=excluded.filename,
                    storage_filename=excluded.storage_filename,
                    uploaded_at=excluded.uploaded_at,
                    storage_backend=excluded.storage_backend,
                    storage_key=excluded.storage_key
                """,
                values,
            )


def delete_template(group_key: str) -> None:
    with common_db.transaction() as (conn, kind):
        conn.execute(
            f"DELETE FROM doc_templates WHERE group_key = {common_db.placeholder(kind)}",
            (group_key,),
        )


def validate_template_file(path: Path, ext: str, max_mb: int, *, pymupdf=None) -> dict:
    """Validate actual DOCX/PDF content, not only the file extension."""
    path = Path(path)
    if not path.exists():
        raise ValueError("檔案不存在")
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("檔案是空的")
    if size > int(max_mb) * 1024 * 1024:
        raise ValueError(f"檔案過大，上限 {int(max_mb)}MB")
    ext = str(ext or "").lower()
    if ext == ".docx":
        if size < 800:
            raise ValueError("DOCX 檔案內容過小，可能已損壞或只是改副檔名")
        try:
            with zipfile.ZipFile(path, "r") as archive:
                names = set(archive.namelist())
                required = {"[Content_Types].xml", "word/document.xml"}
                if not required.issubset(names):
                    raise ValueError("檔案不是有效的 Word DOCX 結構")
                bad = archive.testzip()
                if bad:
                    raise ValueError(f"DOCX 壓縮結構損壞：{bad}")
                ET.fromstring(archive.read("word/document.xml"))
        except ValueError:
            raise
        except (zipfile.BadZipFile, ET.ParseError, OSError) as exc:
            raise ValueError(f"DOCX 檔案損壞或格式不正確：{exc}") from exc
        return {"kind": "docx", "sizeBytes": size}
    if ext == ".pdf":
        head = path.read_bytes()[:8]
        if not head.startswith(b"%PDF-"):
            raise ValueError("檔案內容不是有效 PDF，請勿只修改副檔名")
        try:
            if pymupdf is not None:
                doc = pymupdf.open(str(path))
                pages = doc.page_count
                doc.close()
                if pages < 1:
                    raise ValueError("PDF 沒有可讀頁面")
            else:
                if b"%%EOF" not in path.read_bytes()[-2048:]:
                    raise ValueError("PDF 結構不完整或已損壞")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"PDF 無法解析：{exc}") from exc
        return {"kind": "pdf", "sizeBytes": size}
    raise ValueError("不支援的範本格式")


__all__ = [
    "DOC_TEMPLATE_ALLOWED_EXT",
    "delete_template",
    "get_template",
    "init_schema",
    "list_templates",
    "save_template",
    "validate_template_file",
]
