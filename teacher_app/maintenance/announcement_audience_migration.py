"""0116: scoped teaching/system announcements."""
from __future__ import annotations

from teacher_app.maintenance.migrations import _add_columns, _table_exists, migration


@migration("0116-announcement-audience")
def announcement_audience_116(conn, kind: str) -> None:
    if not _table_exists(conn, kind, "announcements"):
        return

    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_false = "FALSE" if kind == "postgres" else "0"
    _add_columns(
        conn,
        kind,
        "announcements",
        {
            "kind": "kind TEXT NOT NULL DEFAULT 'system'",
            "scope_type": "scope_type TEXT NOT NULL DEFAULT 'all'",
            "training_area": "training_area TEXT NOT NULL DEFAULT ''",
            "group_key": "group_key TEXT NOT NULL DEFAULT ''",
            "course_id": "course_id TEXT NOT NULL DEFAULT ''",
            "starts_at": "starts_at TEXT NOT NULL DEFAULT ''",
            "ends_at": "ends_at TEXT NOT NULL DEFAULT ''",
            "pinned": f"pinned {boolean} NOT NULL DEFAULT {default_false}",
            "email_enabled": f"email_enabled {boolean} NOT NULL DEFAULT {default_false}",
            "require_read": f"require_read {boolean} NOT NULL DEFAULT {default_false}",
            "created_by": "created_by TEXT NOT NULL DEFAULT ''",
        },
    )
    # Historical announcements were created only from system management.
    # Preserve their global visibility and ownership semantics after the split.
    conn.execute(
        "UPDATE announcements SET kind='system' "
        "WHERE kind IS NULL OR TRIM(kind)=''"
    )
    conn.execute(
        "UPDATE announcements SET scope_type='all' "
        "WHERE scope_type IS NULL OR TRIM(scope_type)=''"
    )


__all__ = ["announcement_audience_116"]
