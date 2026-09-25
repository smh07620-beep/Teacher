"""Release migration for learner course feedback."""
from __future__ import annotations

from teacher_app.maintenance.migrations import migration


@migration("0087-course-feedback")
def course_feedback_87(conn, kind: str) -> None:
    """Persist one editable learner feedback row per course and account."""
    del kind
    conn.execute(
        "CREATE TABLE IF NOT EXISTS course_feedback ("
        "course_id TEXT NOT NULL,username TEXT NOT NULL,"
        "rating INTEGER NOT NULL,comment TEXT NOT NULL DEFAULT '',"
        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,"
        "PRIMARY KEY(course_id,username))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_course_feedback_course_updated "
        "ON course_feedback(course_id,updated_at)"
    )


__all__ = ["course_feedback_87"]
