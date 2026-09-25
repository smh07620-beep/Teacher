"""Release migration for material version history and retraining semantics."""
from __future__ import annotations

import json

from teacher_app.maintenance.migrations import _add_columns, migration, utcnow


def _baseline_snapshot(row) -> str:
    try:
        payload = dict(row)
    except Exception:
        payload = {}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


@migration("0084-material-version-retraining")
def material_version_retraining_84(conn, kind: str) -> None:
    """Add immutable material versions and version-aware completion snapshots."""
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_false = "FALSE" if kind == "postgres" else "0"

    _add_columns(
        conn,
        kind,
        "materials",
        {
            "current_version": "current_version INTEGER NOT NULL DEFAULT 1",
            "required_completion_version": "required_completion_version INTEGER NOT NULL DEFAULT 1",
            "version_updated_at": "version_updated_at TEXT NOT NULL DEFAULT ''",
            "version_updated_by": "version_updated_by TEXT NOT NULL DEFAULT ''",
        },
    )
    _add_columns(
        conn,
        kind,
        "material_progress",
        {"completed_version": "completed_version INTEGER NOT NULL DEFAULT 1"},
    )
    _add_columns(
        conn,
        kind,
        "learning_progress",
        {"completed_version": "completed_version INTEGER NOT NULL DEFAULT 1"},
    )

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS material_versions ("
        "material_id TEXT NOT NULL,version INTEGER NOT NULL,"
        f"requires_retraining {boolean} NOT NULL DEFAULT {default_false},"
        "change_reason TEXT NOT NULL DEFAULT '',published_at TEXT NOT NULL,"
        "published_by TEXT NOT NULL DEFAULT '',snapshot TEXT NOT NULL DEFAULT '{}',"
        "PRIMARY KEY(material_id,version))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_material_versions_published "
        "ON material_versions(material_id,published_at)"
    )

    # Existing rows become version 1 without invalidating historical completion.
    # This is an append-only baseline; later publication always inserts version 2+.
    try:
        rows = conn.execute("SELECT * FROM materials").fetchall()
    except Exception:
        rows = []
    ph = "%s" if kind == "postgres" else "?"
    baseline_at = utcnow()
    for row in rows:
        item = dict(row)
        material_id = str(item.get("id") or "").strip()
        if not material_id:
            continue
        conn.execute(
            f"UPDATE materials SET version_updated_at={ph},version_updated_by={ph} "
            f"WHERE id={ph} AND (version_updated_at='' OR version_updated_at IS NULL)",
            (baseline_at, "migration", material_id),
        )
        params = (
            material_id,
            1,
            False if kind == "postgres" else 0,
            "0084 baseline",
            baseline_at,
            "migration",
            _baseline_snapshot(row),
        )
        if kind == "postgres":
            conn.execute(
                "INSERT INTO material_versions "
                "(material_id,version,requires_retraining,change_reason,published_at,published_by,snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(material_id,version) DO NOTHING",
                params,
            )
        else:
            conn.execute(
                "INSERT OR IGNORE INTO material_versions "
                "(material_id,version,requires_retraining,change_reason,published_at,published_by,snapshot) "
                f"VALUES ({','.join([ph] * 7)})",
                params,
            )


__all__ = ["material_version_retraining_84"]
