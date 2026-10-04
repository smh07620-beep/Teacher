"""Additive course publication lifecycle for F2 product maturity."""
from teacher_app.maintenance.migrations import _add_columns, migration


@migration("0113-course-lifecycle")
def course_lifecycle_113(conn, kind: str) -> None:
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
    true_value = "TRUE" if kind == "postgres" else "1"
    conn.execute(
        "UPDATE courses SET lifecycle_status="
        f"CASE WHEN active={true_value} THEN 'published' ELSE 'draft' END "
        "WHERE lifecycle_status IS NULL OR TRIM(lifecycle_status)=''"
    )


__all__ = ["course_lifecycle_113"]
