"""Release migration for immutable learner completion certificates."""
from __future__ import annotations

from teacher_app.maintenance.migrations import migration


@migration("0090-completion-certificates")
def completion_certificates_90(conn, kind: str) -> None:
    """Persist append-only course completion evidence snapshots."""
    del kind
    conn.execute(
        "CREATE TABLE IF NOT EXISTS course_completion_certificates ("
        "id TEXT PRIMARY KEY,username TEXT NOT NULL,emp_id TEXT NOT NULL,"
        "learner_name TEXT NOT NULL,course_id TEXT NOT NULL,course_title TEXT NOT NULL,"
        "training_area TEXT NOT NULL,group_key TEXT NOT NULL,"
        "completion_fingerprint TEXT NOT NULL,evidence_json TEXT NOT NULL DEFAULT '{}',"
        "issued_at TEXT NOT NULL,"
        "UNIQUE(username,course_id,completion_fingerprint))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_completion_certificates_user_issued "
        "ON course_completion_certificates(username,issued_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_completion_certificates_course "
        "ON course_completion_certificates(course_id,issued_at)"
    )


__all__ = ["completion_certificates_90"]
