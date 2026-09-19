"""Canonical pre-migration schema for legacy material completion records."""
from __future__ import annotations

from typing import Any


def init_schema(conn: Any, kind: str) -> None:
    del kind
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_progress (
            emp_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            material_id TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            PRIMARY KEY (emp_id, material_id)
        )
        """
    )


__all__ = ["init_schema"]
