"""Canonical announcement persistence and legacy JSON projection."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Mapping

from teacher_app.common import db as common_db


def row_to_dict(row: Mapping[str, Any] | Any) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": str(data.get("id", "")),
        "title": str(data.get("title", "")),
        "body": str(data.get("body", "")),
        "active": bool(data.get("active", True)),
        "createdAt": str(data.get("created_at", "")),
        "publishedAt": str(data.get("published_at", "")),
    }


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def list_public(limit: int = 8) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(50, int(limit)))
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM announcements WHERE active={ph} "
            f"ORDER BY published_at DESC, created_at DESC LIMIT {bounded_limit}",
            (True if kind == "postgres" else 1,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def list_admin() -> list[dict[str, Any]]:
    with common_db.read_connection() as (conn, _kind):
        rows = conn.execute(
            "SELECT * FROM announcements ORDER BY created_at DESC"
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def create(data: Mapping[str, Any]) -> dict[str, Any]:
    title = str(data.get("title", "")).strip()[:200]
    body = str(data.get("body", "")).strip()[:4000]
    if not title:
        raise ValueError("公告標題不能空白")

    announcement_id = uuid.uuid4().hex
    now = _utc_now_iso()
    active = bool(data.get("active", True))
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"INSERT INTO announcements "
            f"(id,title,body,active,created_at,published_at) "
            f"VALUES ({','.join([ph] * 6)})",
            (
                announcement_id,
                title,
                body,
                active if kind == "postgres" else int(active),
                now,
                now if active else "",
            ),
        )
        row = conn.execute(
            f"SELECT * FROM announcements WHERE id={ph}",
            (announcement_id,),
        ).fetchone()
    return row_to_dict(row)


def update(announcement_id: str, data: Mapping[str, Any]) -> dict[str, Any] | None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM announcements WHERE id={ph}",
            (announcement_id,),
        ).fetchone()
        if not row:
            return None

        old = row_to_dict(row)
        title = str(data.get("title", old["title"])).strip()[:200]
        body = str(data.get("body", old["body"])).strip()[:4000]
        active = bool(data.get("active", old["active"]))
        if not title:
            raise ValueError("公告標題不能空白")
        published = old["publishedAt"] or (_utc_now_iso() if active else "")
        conn.execute(
            f"UPDATE announcements SET title={ph},body={ph},active={ph},"
            f"published_at={ph} WHERE id={ph}",
            (
                title,
                body,
                active if kind == "postgres" else int(active),
                published,
                announcement_id,
            ),
        )
        row = conn.execute(
            f"SELECT * FROM announcements WHERE id={ph}",
            (announcement_id,),
        ).fetchone()
    return row_to_dict(row)


def delete(announcement_id: str) -> bool:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT id FROM announcements WHERE id={ph}",
            (announcement_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            f"DELETE FROM announcements WHERE id={ph}",
            (announcement_id,),
        )
    return True


__all__ = ["create", "delete", "list_admin", "list_public", "row_to_dict", "update"]
