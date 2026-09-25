"""Release migration registration for general learning assignments.

The canonical registry remains :mod:`teacher_app.maintenance.migrations`; this
module contributes the 0083 migration while keeping assignment DDL beside the
learning domain that owns the resulting data model.
"""
from __future__ import annotations

from teacher_app.maintenance.migrations import migration


@migration("0083-learning-assignments")
def learning_assignments_83(conn, kind: str) -> None:
    """Create additive course assignment state for individual/group/all targets."""
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_true = "TRUE" if kind == "postgres" else "1"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS learning_assignments (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL,
            training_area TEXT NOT NULL DEFAULT 'internal',
            group_key TEXT NOT NULL DEFAULT 'grpBio',
            assignee_type TEXT NOT NULL,
            assignee_key TEXT NOT NULL DEFAULT '',
            required {boolean} NOT NULL DEFAULT {default_true},
            due_at TEXT NOT NULL DEFAULT '',
            assigned_at TEXT NOT NULL,
            assigned_by TEXT NOT NULL DEFAULT '',
            active {boolean} NOT NULL DEFAULT {default_true},
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(course_id, assignee_type, assignee_key)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_assignments_assignee "
        "ON learning_assignments(active,assignee_type,assignee_key,training_area,group_key)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_assignments_course "
        "ON learning_assignments(course_id,active)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_assignments_due "
        "ON learning_assignments(active,required,due_at)"
    )


__all__ = ["learning_assignments_83"]
