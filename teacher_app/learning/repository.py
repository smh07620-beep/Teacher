"""Canonical smart-learning persistence.

All learning-progress and material-search SQL lives here and uses the shared
Teacher connection/transaction seam.
"""
from __future__ import annotations

import json
from typing import Iterable

from teacher_app.common import db as common_db


def get_progress(material_id: str, username: str) -> dict:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM learning_progress WHERE material_id={ph} AND username={ph}",
            (material_id, username),
        ).fetchone()
    return dict(row) if row else {}


def upsert_progress(
    material_id: str,
    username: str,
    *,
    position: dict,
    progress: float,
    completed: bool,
    last_viewed_at: str,
    completed_at: str,
) -> None:
    with common_db.transaction() as (conn, kind):
        if kind == "postgres":
            conn.execute(
                "INSERT INTO learning_progress(material_id,username,position,progress,completed,last_viewed_at,completed_at) "
                "VALUES(%s,%s,%s::jsonb,%s,%s,%s,%s) "
                "ON CONFLICT(material_id,username) DO UPDATE SET "
                "position=EXCLUDED.position,progress=EXCLUDED.progress,"
                "completed=learning_progress.completed OR EXCLUDED.completed,"
                "last_viewed_at=EXCLUDED.last_viewed_at,"
                "completed_at=CASE WHEN EXCLUDED.completed THEN EXCLUDED.last_viewed_at ELSE learning_progress.completed_at END",
                (
                    material_id,
                    username,
                    json.dumps(position, ensure_ascii=False),
                    progress,
                    completed,
                    last_viewed_at,
                    completed_at,
                ),
            )
        else:
            conn.execute(
                "INSERT INTO learning_progress(material_id,username,position,progress,completed,last_viewed_at,completed_at) "
                "VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(material_id,username) DO UPDATE SET "
                "position=excluded.position,progress=excluded.progress,"
                "completed=MAX(learning_progress.completed,excluded.completed),"
                "last_viewed_at=excluded.last_viewed_at,"
                "completed_at=CASE WHEN excluded.completed=1 THEN excluded.last_viewed_at ELSE learning_progress.completed_at END",
                (
                    material_id,
                    username,
                    json.dumps(position, ensure_ascii=False),
                    progress,
                    int(completed),
                    last_viewed_at,
                    completed_at,
                ),
            )


def update_media_progress(
    material_id: str,
    username: str,
    *,
    last_position_seconds: float,
    duration: float,
    watched_buckets: list[int],
    completion_threshold: float,
    updated_at: str,
) -> None:
    """Additive 6.8 fields stay a separate update for old test DB compatibility."""
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"UPDATE learning_progress SET last_position_seconds={ph},duration={ph},watched_buckets={ph},"
            f"completion_threshold={ph},updated_at={ph} WHERE material_id={ph} AND username={ph}",
            (
                last_position_seconds,
                duration,
                json.dumps(watched_buckets),
                completion_threshold,
                updated_at,
                material_id,
                username,
            ),
        )


def search_material(material_id: str, query: str, limit: int = 50) -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT page_no,title,text FROM material_text_index "
            f"WHERE material_id={ph} AND LOWER(text) LIKE {ph} ORDER BY page_no LIMIT {int(limit)}",
            (material_id, "%" + query.lower() + "%"),
        ).fetchall()
    return [dict(row) for row in rows]


def get_material_text_rows(material_id: str, limit: int = 100) -> list[dict]:
    """Return bounded indexed text rows for cross-resource search aggregation."""
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT page_no,title,text FROM material_text_index "
            f"WHERE material_id={ph} ORDER BY page_no LIMIT {int(limit)}",
            (material_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_index_status(material_id: str) -> dict:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT status,page_count,last_indexed_at,failure_reason,source_kind "
            f"FROM material_search_status WHERE material_id={ph}",
            (material_id,),
        ).fetchone()
    return dict(row) if row else {}


def write_terminal_status(
    material_id: str,
    status: str,
    *,
    page_count: int,
    indexed_at: str,
    reason: str,
    source_kind: str,
) -> None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        if kind == "postgres":
            conn.execute(
                "INSERT INTO material_search_status(material_id,status,page_count,last_indexed_at,failure_reason,source_kind) "
                "VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(material_id) DO UPDATE SET "
                "status=EXCLUDED.status,page_count=EXCLUDED.page_count,last_indexed_at=EXCLUDED.last_indexed_at,"
                "failure_reason=EXCLUDED.failure_reason,source_kind=EXCLUDED.source_kind",
                (material_id, status, page_count, indexed_at, reason, source_kind),
            )
        else:
            conn.execute(
                "INSERT INTO material_search_status(material_id,status,page_count,last_indexed_at,failure_reason,source_kind) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(material_id) DO UPDATE SET "
                "status=excluded.status,page_count=excluded.page_count,last_indexed_at=excluded.last_indexed_at,"
                "failure_reason=excluded.failure_reason,source_kind=excluded.source_kind",
                (material_id, status, page_count, indexed_at, reason, source_kind),
            )


def replace_text_index(
    material_id: str,
    rows: Iterable[tuple[int, str, str]],
    *,
    indexed_at: str,
    status: str,
    reason: str,
    source_kind: str,
) -> int:
    material_rows = list(rows)
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(f"DELETE FROM material_text_index WHERE material_id={ph}", (material_id,))
        for page_no, text, title in material_rows:
            conn.execute(
                f"INSERT INTO material_text_index(material_id,page_no,title,text,indexed_at) "
                f"VALUES({ph},{ph},{ph},{ph},{ph})",
                (material_id, page_no, title, text, indexed_at),
            )
        if kind == "postgres":
            conn.execute(
                "INSERT INTO material_search_status(material_id,status,page_count,last_indexed_at,failure_reason,source_kind) "
                "VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(material_id) DO UPDATE SET "
                "status=EXCLUDED.status,page_count=EXCLUDED.page_count,last_indexed_at=EXCLUDED.last_indexed_at,"
                "failure_reason=EXCLUDED.failure_reason,source_kind=EXCLUDED.source_kind",
                (material_id, status, len(material_rows), indexed_at, reason, source_kind),
            )
        else:
            conn.execute(
                "INSERT INTO material_search_status(material_id,status,page_count,last_indexed_at,failure_reason,source_kind) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(material_id) DO UPDATE SET "
                "status=excluded.status,page_count=excluded.page_count,last_indexed_at=excluded.last_indexed_at,"
                "failure_reason=excluded.failure_reason,source_kind=excluded.source_kind",
                (material_id, status, len(material_rows), indexed_at, reason, source_kind),
            )
    return len(material_rows)
