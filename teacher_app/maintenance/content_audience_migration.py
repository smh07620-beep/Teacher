"""0096: separate content ownership from learner audience visibility."""
from __future__ import annotations

from teacher_app.maintenance.migrations import migration


def _column_exists(conn, kind: str, table: str, column: str) -> bool:
    if kind == "postgres":
        return bool(
            conn.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name=%s AND column_name=%s",
                (table, column),
            ).fetchone()
        )
    return any(str(row[1]) == column for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _table_exists(conn, kind: str, table: str) -> bool:
    if kind == "postgres":
        return bool(
            conn.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=current_schema() AND table_name=%s",
                (table,),
            ).fetchone()
        )
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _ensure_audience_columns(conn, kind: str, table: str) -> None:
    if not _table_exists(conn, kind, table):
        return
    if not _column_exists(conn, kind, table, "audience_scope"):
        if kind == "postgres":
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS audience_scope TEXT NOT NULL DEFAULT 'group_only'"
            )
        else:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN audience_scope TEXT NOT NULL DEFAULT 'group_only'"
            )
    if not _column_exists(conn, kind, table, "audience_groups"):
        if kind == "postgres":
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS audience_groups JSONB NOT NULL DEFAULT '[]'::jsonb"
            )
        else:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN audience_groups TEXT NOT NULL DEFAULT '[]'"
            )
    conn.execute(
        f"UPDATE {table} SET audience_scope='group_only' "
        "WHERE audience_scope IS NULL OR audience_scope=''"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table}_audience_scope ON {table}(audience_scope)"
    )


@migration("0096-content-audience-scope")
def content_audience_scope_96(conn, kind: str) -> None:
    # Ownership remains group_key (materials) or the owning quiz category
    # (questions). These new columns only decide who may consume/reuse content.
    _ensure_audience_columns(conn, kind, "materials")
    _ensure_audience_columns(conn, kind, "quiz_questions")


__all__ = ["content_audience_scope_96"]
