"""Canonical pre-migration schema for uploaded materials."""
from __future__ import annotations

from typing import Any


def _columns(conn: Any, kind: str, table: str) -> set[str]:
    if kind == "postgres":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=%s",
            (table,),
        ).fetchall()
        return {str(dict(row).get("column_name") or "").lower() for row in rows}
    return {str(row[1]).lower() for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_missing(conn: Any, kind: str, definitions: dict[str, str]) -> None:
    existing = _columns(conn, kind, "materials")
    for name, definition in definitions.items():
        if name in existing:
            continue
        if kind == "postgres":
            conn.execute(f"ALTER TABLE materials ADD COLUMN IF NOT EXISTS {definition}")
        else:
            conn.execute(f"ALTER TABLE materials ADD COLUMN {definition}")


def init_schema(conn: Any, kind: str) -> None:
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_true = "TRUE" if kind == "postgres" else "1"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS materials (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '',
            group_key TEXT NOT NULL DEFAULT 'grpBio',
            training_area TEXT NOT NULL DEFAULT 'internal',
            course_id TEXT NOT NULL DEFAULT '',
            folder TEXT NOT NULL,
            page_count INTEGER NOT NULL DEFAULT 0,
            date_added TEXT NOT NULL,
            storage_filename TEXT NOT NULL,
            storage_backend TEXT NOT NULL DEFAULT 'local',
            storage_key TEXT NOT NULL DEFAULT '',
            slides_prefix TEXT NOT NULL DEFAULT '',
            storage_meta TEXT NOT NULL DEFAULT '{{}}',
            material_type TEXT NOT NULL DEFAULT 'standard',
            atlas_meta TEXT NOT NULL DEFAULT '{{}}',
            current_version INTEGER NOT NULL DEFAULT 1,
            required_completion_version INTEGER NOT NULL DEFAULT 1,
            version_updated_at TEXT NOT NULL DEFAULT '',
            version_updated_by TEXT NOT NULL DEFAULT '',
            active {boolean} NOT NULL DEFAULT {default_true}
        )
        """
    )
    _add_missing(
        conn,
        kind,
        {
            "group_key": "group_key TEXT NOT NULL DEFAULT 'grpBio'",
            "training_area": "training_area TEXT NOT NULL DEFAULT 'internal'",
            "course_id": "course_id TEXT NOT NULL DEFAULT ''",
            "storage_backend": "storage_backend TEXT NOT NULL DEFAULT 'local'",
            "storage_key": "storage_key TEXT NOT NULL DEFAULT ''",
            "slides_prefix": "slides_prefix TEXT NOT NULL DEFAULT ''",
            "storage_meta": "storage_meta TEXT NOT NULL DEFAULT '{}'",
            "material_type": "material_type TEXT NOT NULL DEFAULT 'standard'",
            "atlas_meta": "atlas_meta TEXT NOT NULL DEFAULT '{}'",
            "current_version": "current_version INTEGER NOT NULL DEFAULT 1",
            "required_completion_version": "required_completion_version INTEGER NOT NULL DEFAULT 1",
            "version_updated_at": "version_updated_at TEXT NOT NULL DEFAULT ''",
            "version_updated_by": "version_updated_by TEXT NOT NULL DEFAULT ''",
        },
    )


__all__ = ["init_schema"]
