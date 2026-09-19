"""Canonical pre-0068 schema for quiz categories, questions and publications."""
from __future__ import annotations

from typing import Any

from teacher_app.assessments import ai_job_schema


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
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_true = "TRUE" if kind == "postgres" else "1"
    default_false = "FALSE" if kind == "postgres" else "0"
    json_type = "JSONB" if kind == "postgres" else "TEXT"
    json_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS quiz_categories (
            id TEXT PRIMARY KEY,
            group_key TEXT NOT NULL DEFAULT 'grpBio',
            training_area TEXT NOT NULL DEFAULT 'internal',
            course_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            date_added TEXT NOT NULL,
            active {boolean} NOT NULL DEFAULT {default_true},
            blind_mode {boolean} NOT NULL DEFAULT {default_false},
            draw_count INTEGER NOT NULL DEFAULT 0,
            passing_score INTEGER NOT NULL DEFAULT 80,
            audience TEXT NOT NULL DEFAULT '',
            draw_rules {json_type} NOT NULL DEFAULT {json_default},
            review_status TEXT NOT NULL DEFAULT 'approved',
            reviewer_name TEXT NOT NULL DEFAULT '',
            reviewer_title TEXT NOT NULL DEFAULT '',
            reviewed_at TEXT NOT NULL DEFAULT '',
            published_at TEXT NOT NULL DEFAULT '',
            publication_id TEXT NOT NULL DEFAULT '',
            publication_hash TEXT NOT NULL DEFAULT ''
        )
        """
    )
    _add_missing(
        conn,
        kind,
        "quiz_categories",
        {
            "training_area": "training_area TEXT NOT NULL DEFAULT 'internal'",
            "course_id": "course_id TEXT NOT NULL DEFAULT ''",
            "blind_mode": f"blind_mode {boolean} NOT NULL DEFAULT {default_false}",
            "draw_count": "draw_count INTEGER NOT NULL DEFAULT 0",
            "passing_score": "passing_score INTEGER NOT NULL DEFAULT 80",
            "audience": "audience TEXT NOT NULL DEFAULT ''",
            "draw_rules": f"draw_rules {json_type} NOT NULL DEFAULT {json_default}",
            "review_status": "review_status TEXT NOT NULL DEFAULT 'approved'",
            "reviewer_name": "reviewer_name TEXT NOT NULL DEFAULT ''",
            "reviewer_title": "reviewer_title TEXT NOT NULL DEFAULT ''",
            "reviewed_at": "reviewed_at TEXT NOT NULL DEFAULT ''",
            "published_at": "published_at TEXT NOT NULL DEFAULT ''",
            "publication_id": "publication_id TEXT NOT NULL DEFAULT ''",
            "publication_hash": "publication_hash TEXT NOT NULL DEFAULT ''",
        },
    )
    ai_job_schema.init_schema(conn, kind)

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS quiz_publications (
            id TEXT PRIMARY KEY,
            quiz_category_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reviewer_name TEXT NOT NULL DEFAULT '',
            snapshot_hash TEXT NOT NULL,
            snapshot {json_type} NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_quiz_publications_category "
        "ON quiz_publications(quiz_category_id, created_at DESC)"
    )

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS quiz_questions (
            id TEXT PRIMARY KEY,
            quiz_category_id TEXT NOT NULL,
            tag TEXT NOT NULL DEFAULT '',
            question TEXT NOT NULL,
            question_type TEXT NOT NULL DEFAULT 'choice',
            image_url TEXT NOT NULL DEFAULT '',
            options {json_type} NOT NULL,
            correct INTEGER NOT NULL DEFAULT 0,
            answer_config {json_type} NOT NULL DEFAULT {json_default},
            explanation TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            active {boolean} NOT NULL DEFAULT {default_true},
            difficulty TEXT NOT NULL DEFAULT 'standard'
        )
        """
    )
    _add_missing(
        conn,
        kind,
        "quiz_questions",
        {
            "active": f"active {boolean} NOT NULL DEFAULT {default_true}",
            "answer_config": f"answer_config {json_type} NOT NULL DEFAULT {json_default}",
            "difficulty": "difficulty TEXT NOT NULL DEFAULT 'standard'",
        },
    )


__all__ = ["init_schema"]
