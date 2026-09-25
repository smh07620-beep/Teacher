"""Release migration registration for material version and retraining evidence.

The canonical migration registry remains :mod:`teacher_app.maintenance.migrations`.
This module owns additive 0084 DDL so material versioning can evolve without
rewriting historical learner completion records.
"""
from __future__ import annotations

import json

from teacher_app.maintenance.migrations import migration, utcnow


def _table_exists(conn, kind: str, table: str) -> bool:
    if kind == "postgres":
        row = conn.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema=current_schema() AND table_name=%s",
            (table,),
        ).fetchone()
        return bool(row)
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _columns(conn, kind: str, table: str) -> set[str]:
    if not _table_exists(conn, kind, table):
        return set()
    if kind == "postgres":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=%s",
            (table,),
        ).fetchall()
        return {str(dict(row).get("column_name") or "").lower() for row in rows}
    return {str(row[1]).lower() for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column(conn, kind: str, table: str, name: str, definition: str) -> None:
    if not _table_exists(conn, kind, table):
        return
    if name in _columns(conn, kind, table):
        return
    if kind == "postgres":
        conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {definition}")
    else:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


@migration("0084-material-version-retraining")
def material_version_retraining_84(conn, kind: str) -> None:
    """Add immutable material-version evidence and version-aware completion snapshots."""
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_false = "FALSE" if kind == "postgres" else "0"
    payload = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"

    _add_column(conn, kind, "materials", "current_version", "current_version INTEGER NOT NULL DEFAULT 1")
    _add_column(
        conn,
        kind,
        "materials",
        "required_completion_version",
        "required_completion_version INTEGER NOT NULL DEFAULT 1",
    )
    _add_column(conn, kind, "materials", "version_updated_at", "version_updated_at TEXT NOT NULL DEFAULT ''")
    _add_column(conn, kind, "materials", "version_updated_by", "version_updated_by TEXT NOT NULL DEFAULT ''")
    _add_column(
        conn,
        kind,
        "material_progress",
        "completed_version",
        "completed_version INTEGER NOT NULL DEFAULT 1",
    )
    _add_column(
        conn,
        kind,
        "learning_progress",
        "completed_version",
        "completed_version INTEGER NOT NULL DEFAULT 1",
    )

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS material_versions (
            material_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            snapshot {payload} NOT NULL DEFAULT {payload_default},
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL DEFAULT '',
            change_reason TEXT NOT NULL DEFAULT '',
            requires_retraining {boolean} NOT NULL DEFAULT {default_false},
            PRIMARY KEY(material_id, version)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_material_versions_created "
        "ON material_versions(material_id,created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_material_versions_retraining "
        "ON material_versions(requires_retraining,created_at)"
    )

    if not _table_exists(conn, kind, "materials"):
        return
    rows = conn.execute("SELECT * FROM materials").fetchall()
    ph = "%s" if kind == "postgres" else "?"
    for row in rows:
        item = dict(row)
        material_id = str(item.get("id") or "")
        if not material_id:
            continue
        version = max(1, int(item.get("current_version") or 1))
        exists = conn.execute(
            f"SELECT 1 FROM material_versions WHERE material_id={ph} AND version={ph}",
            (material_id, version),
        ).fetchone()
        if exists:
            continue
        snapshot = json.dumps(item, ensure_ascii=False, default=str)
        if kind == "postgres":
            conn.execute(
                "INSERT INTO material_versions "
                "(material_id,version,snapshot,created_at,created_by,change_reason,requires_retraining) "
                "VALUES (%s,%s,%s::jsonb,%s,%s,%s,FALSE)",
                (material_id, version, snapshot, utcnow(), "migration-0084", "0084 baseline"),
            )
        else:
            conn.execute(
                "INSERT INTO material_versions "
                "(material_id,version,snapshot,created_at,created_by,change_reason,requires_retraining) "
                "VALUES (?,?,?,?,?,?,0)",
                (material_id, version, snapshot, utcnow(), "migration-0084", "0084 baseline"),
            )


__all__ = ["material_version_retraining_84"]
