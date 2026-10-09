"""Per-exam assignee list (individual / group / everyone)."""
from teacher_app.maintenance.migrations import migration


@migration("0117-exam-assignees")
def exam_assignees_117(conn, kind: str) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS exam_assignees (
        quiz_category_id TEXT NOT NULL,
        assignee_type TEXT NOT NULL,
        assignee_key TEXT NOT NULL DEFAULT '',
        assigned_by TEXT NOT NULL DEFAULT '',
        assigned_at TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (quiz_category_id, assignee_type, assignee_key)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exam_assignees_user ON exam_assignees(assignee_type, assignee_key)")
