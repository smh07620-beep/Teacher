"""Per-account email notification category preferences."""
from teacher_app.maintenance.migrations import migration


@migration("0106-notification-email-preferences")
def notification_email_preferences_106(conn, kind: str) -> None:
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_true = "TRUE" if kind == "postgres" else "1"
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS notification_email_preferences (
            username TEXT PRIMARY KEY,
            email_course_due {boolean} NOT NULL DEFAULT {default_true},
            email_exam_due {boolean} NOT NULL DEFAULT {default_true},
            email_retraining {boolean} NOT NULL DEFAULT {default_true},
            email_teacher_review {boolean} NOT NULL DEFAULT {default_true},
            updated_at TEXT NOT NULL DEFAULT ''
        )"""
    )


__all__ = ["notification_email_preferences_106"]
