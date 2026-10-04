"""Persist manager-owned training intervention cases for F3."""
from __future__ import annotations

from teacher_app.maintenance.migrations import migration


@migration("0114-training-interventions")
def training_interventions_114(conn, kind: str) -> None:
    del kind
    conn.execute(
        "CREATE TABLE IF NOT EXISTS training_interventions ("
        "id TEXT PRIMARY KEY,"
        "username TEXT NOT NULL,"
        "emp_id TEXT NOT NULL DEFAULT '',"
        "course_id TEXT NOT NULL,"
        "source_status TEXT NOT NULL,"
        "kind TEXT NOT NULL,"
        "status TEXT NOT NULL DEFAULT 'open',"
        "learner_message TEXT NOT NULL DEFAULT '',"
        "internal_note TEXT NOT NULL DEFAULT '',"
        "plan_json TEXT NOT NULL DEFAULT '{}',"
        "created_by TEXT NOT NULL DEFAULT '',"
        "created_at TEXT NOT NULL,"
        "updated_by TEXT NOT NULL DEFAULT '',"
        "updated_at TEXT NOT NULL,"
        "resolved_at TEXT NOT NULL DEFAULT '',"
        "resolution_json TEXT NOT NULL DEFAULT '{}'"
        ")"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_training_interventions_user_status "
        "ON training_interventions(username,status,updated_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_training_interventions_course_status "
        "ON training_interventions(course_id,status,updated_at)"
    )


__all__ = ["training_interventions_114"]
