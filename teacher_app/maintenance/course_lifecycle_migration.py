"""Additive course publication lifecycle for F2 product maturity."""
from teacher_app.maintenance.migrations import _add_columns, _columns, _table_exists, migration


@migration("0113-course-lifecycle")
def course_lifecycle_113(conn, kind: str) -> None:
    # Some upgrade/health tests intentionally run migrations against a minimal
    # legacy schema where courses does not exist yet. The canonical course
    # schema owner will add these columns if the table is introduced later.
    if not _table_exists(conn, kind, "courses"):
        return

    _add_columns(
        conn,
        kind,
        "courses",
        {
            "lifecycle_status": "lifecycle_status TEXT NOT NULL DEFAULT ''",
            "published_at": "published_at TEXT NOT NULL DEFAULT ''",
            "ended_at": "ended_at TEXT NOT NULL DEFAULT ''",
            "archived_at": "archived_at TEXT NOT NULL DEFAULT ''",
            "lifecycle_updated_at": "lifecycle_updated_at TEXT NOT NULL DEFAULT ''",
            "lifecycle_updated_by": "lifecycle_updated_by TEXT NOT NULL DEFAULT ''",
        },
    )

    columns = _columns(conn, kind, "courses")
    if "lifecycle_status" not in columns:
        return

    # Preserve legacy visibility. Old course schemas normally have active;
    # reduced compatibility fixtures may not. In the latter case, treating
    # existing rows as published is the least destructive migration behavior.
    if "active" in columns:
        true_value = "TRUE" if kind == "postgres" else "1"
        conn.execute(
            "UPDATE courses SET lifecycle_status="
            f"CASE WHEN active={true_value} THEN 'published' ELSE 'draft' END "
            "WHERE lifecycle_status IS NULL OR TRIM(lifecycle_status)=''"
        )
    else:
        conn.execute(
            "UPDATE courses SET lifecycle_status='published' "
            "WHERE lifecycle_status IS NULL OR TRIM(lifecycle_status)=''"
        )


__all__ = ["course_lifecycle_113"]
