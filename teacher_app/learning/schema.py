"""Canonical pre-migration schema for legacy material completion records."""
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


def init_schema(conn: Any, kind: str) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_progress (
            emp_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            material_id TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            completed_version INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (emp_id, material_id)
        )
        """
    )
    if "completed_version" not in _columns(conn, kind, "material_progress"):
        if kind == "postgres":
            conn.execute(
                "ALTER TABLE material_progress ADD COLUMN IF NOT EXISTS "
                "completed_version INTEGER NOT NULL DEFAULT 1"
            )
        else:
            conn.execute(
                "ALTER TABLE material_progress ADD COLUMN completed_version INTEGER NOT NULL DEFAULT 1"
            )


__all__ = ["init_schema"]
