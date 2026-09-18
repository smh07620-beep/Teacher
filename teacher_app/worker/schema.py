"""Canonical pre-migration schema for the material job queue only."""
from __future__ import annotations

from typing import Any


def _columns(conn: Any, kind: str) -> set[str]:
    if kind == "postgres":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=%s",
            ("material_jobs",),
        ).fetchall()
        return {str(dict(row).get("column_name") or "").lower() for row in rows}
    return {str(row[1]).lower() for row in conn.execute("PRAGMA table_info(material_jobs)").fetchall()}


def init_schema(conn: Any, kind: str) -> None:
    payload = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"
    bytes_type = "BIGINT" if kind == "postgres" else "INTEGER"
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_false = "FALSE" if kind == "postgres" else "0"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS material_jobs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'queued',
            priority INTEGER NOT NULL DEFAULT 50,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            available_at TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            stage TEXT NOT NULL DEFAULT '等待處理',
            detail TEXT NOT NULL DEFAULT '',
            payload {payload} NOT NULL DEFAULT {payload_default},
            staging_path TEXT NOT NULL,
            staging_backend TEXT NOT NULL DEFAULT 'local',
            staging_key TEXT NOT NULL DEFAULT '',
            original_name TEXT NOT NULL DEFAULT '',
            material_id TEXT NOT NULL DEFAULT '',
            source_sha256 TEXT NOT NULL DEFAULT '',
            source_bytes {bytes_type} NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            result {payload} NOT NULL DEFAULT {payload_default},
            worker_id TEXT NOT NULL DEFAULT '',
            worker_last_seen TEXT NOT NULL DEFAULT '',
            cancel_requested {boolean} NOT NULL DEFAULT {default_false},
            cleanup_pending {boolean} NOT NULL DEFAULT {default_false}
        )
        """
    )

    # These five columns are formally 0067 additive ownership, but the current
    # canonical insert statement names them unconditionally.  Keeping this tiny
    # compatibility subset makes direct pre-migration queue inserts valid while
    # the 0067 migrations remain authoritative/idempotent for deployed upgrades.
    existing = _columns(conn, kind)
    definitions = {
        "staging_backend": "staging_backend TEXT NOT NULL DEFAULT 'local'",
        "staging_key": "staging_key TEXT NOT NULL DEFAULT ''",
        "original_name": "original_name TEXT NOT NULL DEFAULT ''",
        "worker_last_seen": "worker_last_seen TEXT NOT NULL DEFAULT ''",
        "cleanup_pending": f"cleanup_pending {boolean} NOT NULL DEFAULT {default_false}",
    }
    for name, definition in definitions.items():
        if name in existing:
            continue
        if kind == "postgres":
            conn.execute(f"ALTER TABLE material_jobs ADD COLUMN IF NOT EXISTS {definition}")
        else:
            conn.execute(f"ALTER TABLE material_jobs ADD COLUMN {definition}")

    if kind == "postgres":
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_material_jobs_queue "
            "ON material_jobs(status, priority DESC, created_at)"
        )
    else:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_material_jobs_queue "
            "ON material_jobs(status, priority, created_at)"
        )


__all__ = ["init_schema"]
