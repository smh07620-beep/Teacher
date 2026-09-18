"""Canonical assessment/category read data access.

This initial repository seam intentionally starts with the small read surface
needed by materials. Assessment mutation ownership will be migrated separately.
"""
from __future__ import annotations

from teacher_app.common import db as common_db
from teacher_app.common import scope


def get_category(category_id: str) -> dict | None:
    if not category_id:
        return None
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT id,title,group_key,training_area,active FROM quiz_categories WHERE id={ph}",
            (category_id,),
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    return {
        "id": str(data.get("id") or ""),
        "title": str(data.get("title") or ""),
        "group": scope.normalize_group(data.get("group_key")),
        "area": scope.normalize_area(data.get("training_area")),
        "active": bool(data.get("active", True)),
    }


def category_labels() -> dict[str, str]:
    with common_db.read_connection() as (conn, _kind):
        rows = conn.execute("SELECT id,title FROM quiz_categories").fetchall()
    return {
        str(dict(row).get("id") or ""): str(dict(row).get("title") or "")
        for row in rows
        if dict(row).get("id")
    }
