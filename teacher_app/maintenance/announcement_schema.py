"""Canonical pre-migration schema for platform announcements."""
from __future__ import annotations

from typing import Any


def init_schema(conn: Any, kind: str) -> None:
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_true = "TRUE" if kind == "postgres" else "1"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS announcements (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            active {boolean} NOT NULL DEFAULT {default_true},
            created_at TEXT NOT NULL,
            published_at TEXT NOT NULL DEFAULT ''
        )
        """
    )


__all__ = ["init_schema"]
