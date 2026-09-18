"""Canonical pre-migration schema for persisted exam records."""
from __future__ import annotations

from typing import Any


def _columns(conn: Any, kind: str, table: str) -> set[str]:
    if kind == "postgres":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=%s",
            (table,),
        ).fetchall()
        return {str(dict(row).get("column_name") or "").lower() for row in rows}
    return {str(row[1]).lower() for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_missing(conn: Any, kind: str, table: str, definitions: dict[str, str]) -> None:
    existing = _columns(conn, kind, table)
    for name, definition in definitions.items():
        if name in existing:
            continue
        if kind == "postgres":
            conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {definition}")
        else:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_schema(conn: Any, kind: str) -> None:
    answers_type = "JSONB" if kind == "postgres" else "TEXT"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS exam_records (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            name TEXT NOT NULL,
            emp_id TEXT NOT NULL,
            role TEXT NOT NULL,
            evaluator_name TEXT,
            evaluator_title TEXT,
            quiz_title TEXT NOT NULL,
            score INTEGER NOT NULL,
            status TEXT NOT NULL,
            correct_count INTEGER NOT NULL DEFAULT 0,
            wrong_count INTEGER NOT NULL DEFAULT 0,
            answers_detail {answers_type} NOT NULL,
            group_key TEXT NOT NULL DEFAULT 'grpBio',
            training_area TEXT NOT NULL DEFAULT 'internal',
            publication_id TEXT NOT NULL DEFAULT '',
            publication_hash TEXT NOT NULL DEFAULT '',
            course_id TEXT NOT NULL DEFAULT '',
            review_status TEXT NOT NULL DEFAULT 'completed',
            reviewed_at TEXT NOT NULL DEFAULT '',
            reviewer_name TEXT NOT NULL DEFAULT '',
            review_comment TEXT NOT NULL DEFAULT '',
            quiz_category_id TEXT NOT NULL DEFAULT '',
            passing_score INTEGER NOT NULL DEFAULT 80
        )
        """
    )
    _add_missing(
        conn,
        kind,
        "exam_records",
        {
            "group_key": "group_key TEXT NOT NULL DEFAULT 'grpBio'",
            "training_area": "training_area TEXT NOT NULL DEFAULT 'internal'",
            "publication_id": "publication_id TEXT NOT NULL DEFAULT ''",
            "publication_hash": "publication_hash TEXT NOT NULL DEFAULT ''",
            "course_id": "course_id TEXT NOT NULL DEFAULT ''",
            "review_status": "review_status TEXT NOT NULL DEFAULT 'completed'",
            "reviewed_at": "reviewed_at TEXT NOT NULL DEFAULT ''",
            "reviewer_name": "reviewer_name TEXT NOT NULL DEFAULT ''",
            "review_comment": "review_comment TEXT NOT NULL DEFAULT ''",
            "quiz_category_id": "quiz_category_id TEXT NOT NULL DEFAULT ''",
            "passing_score": "passing_score INTEGER NOT NULL DEFAULT 80",
        },
    )


__all__ = ["init_schema"]
