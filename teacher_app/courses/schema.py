"""Canonical pre-migration schema for courses and teaching-plan fields."""
from __future__ import annotations

from typing import Any


def _columns(conn: Any, kind: str) -> set[str]:
    if kind == "postgres":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=%s",
            ("courses",),
        ).fetchall()
        return {str(dict(row).get("column_name") or "").lower() for row in rows}
    return {str(row[1]).lower() for row in conn.execute("PRAGMA table_info(courses)").fetchall()}


def init_schema(conn: Any, kind: str) -> None:
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_true = "TRUE" if kind == "postgres" else "1"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS courses (
            id TEXT PRIMARY KEY,
            training_area TEXT NOT NULL DEFAULT 'pgy',
            group_key TEXT NOT NULL DEFAULT 'grpBio',
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            date_added TEXT NOT NULL,
            active {boolean} NOT NULL DEFAULT {default_true},
            learning_objectives TEXT NOT NULL DEFAULT '',
            estimated_minutes INTEGER NOT NULL DEFAULT 0,
            start_date TEXT NOT NULL DEFAULT '',
            end_date TEXT NOT NULL DEFAULT '',
            material_order TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    existing = _columns(conn, kind)
    definitions = {
        "learning_objectives": "learning_objectives TEXT NOT NULL DEFAULT ''",
        "estimated_minutes": "estimated_minutes INTEGER NOT NULL DEFAULT 0",
        "start_date": "start_date TEXT NOT NULL DEFAULT ''",
        "end_date": "end_date TEXT NOT NULL DEFAULT ''",
        "material_order": "material_order TEXT NOT NULL DEFAULT '[]'",
    }
    for name, definition in definitions.items():
        if name in existing:
            continue
        if kind == "postgres":
            conn.execute(f"ALTER TABLE courses ADD COLUMN IF NOT EXISTS {definition}")
        else:
            conn.execute(f"ALTER TABLE courses ADD COLUMN {definition}")


__all__ = ["init_schema"]
