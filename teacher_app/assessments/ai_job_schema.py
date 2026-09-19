"""Persistent schema for asynchronous AI question-generation jobs."""
from __future__ import annotations

from typing import Any


def init_schema(conn: Any, kind: str) -> None:
    payload_type = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS ai_question_jobs (
            id TEXT PRIMARY KEY,
            quiz_category_id TEXT NOT NULL,
            group_key TEXT NOT NULL,
            training_area TEXT NOT NULL,
            actor_username TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            request_json {payload_type} NOT NULL DEFAULT {payload_default},
            progress_percent REAL NOT NULL DEFAULT 0,
            progress_stage TEXT NOT NULL DEFAULT '',
            progress_detail TEXT NOT NULL DEFAULT '',
            result_json {payload_type} NOT NULL DEFAULT {payload_default},
            error TEXT NOT NULL DEFAULT '',
            claim_token TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_question_jobs_queue "
        "ON ai_question_jobs(status, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_question_jobs_actor "
        "ON ai_question_jobs(actor_username, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_question_jobs_scope "
        "ON ai_question_jobs(group_key, training_area, created_at)"
    )


__all__ = ["init_schema"]
