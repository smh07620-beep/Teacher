"""Canonical pre-migration schema for platform announcements."""
from __future__ import annotations

from typing import Any


def init_schema(conn: Any, kind: str) -> None:
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_true = "TRUE" if kind == "postgres" else "1"
    default_false = "FALSE" if kind == "postgres" else "0"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS announcements (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            active {boolean} NOT NULL DEFAULT {default_true},
            created_at TEXT NOT NULL,
            published_at TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'system',
            scope_type TEXT NOT NULL DEFAULT 'all',
            training_area TEXT NOT NULL DEFAULT '',
            group_key TEXT NOT NULL DEFAULT '',
            course_id TEXT NOT NULL DEFAULT '',
            starts_at TEXT NOT NULL DEFAULT '',
            ends_at TEXT NOT NULL DEFAULT '',
            pinned {boolean} NOT NULL DEFAULT {default_false},
            email_enabled {boolean} NOT NULL DEFAULT {default_false},
            require_read {boolean} NOT NULL DEFAULT {default_false},
            created_by TEXT NOT NULL DEFAULT ''
        )
        """
    )


__all__ = ["init_schema"]
