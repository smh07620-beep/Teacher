"""Release migration for cross-device saved learning items."""
from __future__ import annotations

from teacher_app.maintenance.migrations import migration


@migration("0088-saved-learning-items")
def saved_learning_items_88(conn, kind: str) -> None:
    """Persist account-scoped course/material save-for-later markers."""
    del kind
    conn.execute(
        "CREATE TABLE IF NOT EXISTS saved_learning_items ("
        "username TEXT NOT NULL,item_type TEXT NOT NULL,item_id TEXT NOT NULL,"
        "saved_at TEXT NOT NULL,PRIMARY KEY(username,item_type,item_id))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_saved_learning_items_user_saved "
        "ON saved_learning_items(username,saved_at)"
    )


__all__ = ["saved_learning_items_88"]
