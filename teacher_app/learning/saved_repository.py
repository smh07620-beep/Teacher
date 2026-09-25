"""Persistence for account-scoped saved learning items."""
from __future__ import annotations

from teacher_app.common import db as common_db


def list_saved(username: str) -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT item_type,item_id,saved_at FROM saved_learning_items WHERE username={ph} ORDER BY saved_at DESC LIMIT 200",
            (username,),
        ).fetchall()
    return [
        {"itemType": str(dict(row).get("item_type") or ""), "itemId": str(dict(row).get("item_id") or ""), "savedAt": str(dict(row).get("saved_at") or "")}
        for row in rows
    ]


def set_saved(username: str, item_type: str, item_id: str, *, saved: bool, now: str) -> None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        if not saved:
            conn.execute(
                f"DELETE FROM saved_learning_items WHERE username={ph} AND item_type={ph} AND item_id={ph}",
                (username, item_type, item_id),
            )
            return
        conn.execute(
            f"INSERT INTO saved_learning_items (username,item_type,item_id,saved_at) VALUES ({','.join([ph] * 4)}) "
            "ON CONFLICT(username,item_type,item_id) DO UPDATE SET saved_at=excluded.saved_at",
            (username, item_type, item_id, now),
        )


__all__ = ["list_saved", "set_saved"]
