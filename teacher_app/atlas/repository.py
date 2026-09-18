"""Canonical persistence for Atlas items.

This module owns Atlas row projection and runtime CRUD SQL.  HTTP, image-file
transport and DOCX parsing stay outside the repository.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from teacher_app.common import db as common_db


ATLAS_COLUMNS = (
    "id", "category", "group_key", "title", "image_url", "description",
    "tags", "differential_points", "teaching_notes", "difficulty",
    "published", "source", "source_material_id", "source_docx", "sort_order",
    "annotation_json", "created_at", "updated_at", "created_by", "updated_by",
)


def row_to_item(row: Any) -> dict:
    item = dict(row) if row is not None else {}
    if not item:
        return {}
    try:
        item["tags"] = json.loads(item.get("tags") or "[]")
    except Exception:
        item["tags"] = []
    try:
        item["annotationJson"] = json.loads(item.pop("annotation_json", "{}") or "{}")
    except Exception:
        item["annotationJson"] = {}
    item["group"] = item.pop("group_key", "")
    item["imageUrl"] = item.pop("image_url", "")
    item["thumbnailUrl"] = (
        item["imageUrl"].replace("/api/atlas/images/", "/api/atlas/images/thumb-")
        if item["imageUrl"].startswith("/api/atlas/images/")
        else item["imageUrl"]
    )
    item["differentialPoints"] = item.pop("differential_points", "")
    item["teachingNotes"] = item.pop("teaching_notes", "")
    item["sourceMaterialId"] = item.pop("source_material_id", "")
    item["sourceDocx"] = item.pop("source_docx", "")
    item["sortOrder"] = item.pop("sort_order", 0)
    item["createdAt"] = item.pop("created_at", "")
    item["updatedAt"] = item.pop("updated_at", "")
    item["createdBy"] = item.pop("created_by", "")
    item["updatedBy"] = item.pop("updated_by", "")
    item["published"] = bool(item.get("published"))
    return item


def list_items() -> list[dict]:
    with common_db.read_connection() as (conn, _kind):
        rows = conn.execute(
            "SELECT * FROM atlas_items ORDER BY sort_order,title,id"
        ).fetchall()
    return [row_to_item(row) for row in rows]


def get_item(item_id: str) -> dict:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM atlas_items WHERE id={ph}",
            (str(item_id),),
        ).fetchone()
    return row_to_item(row)


def get_image_access(image_url: str) -> dict:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT group_key,published FROM atlas_items WHERE image_url={ph}",
            (str(image_url),),
        ).fetchone()
    return dict(row) if row is not None else {}


def insert_item_on_connection(conn, kind: str, values: Mapping[str, Any]) -> str:
    ph = common_db.placeholder(kind)
    item_id = str(values["id"])
    conn.execute(
        "INSERT INTO atlas_items(" + ",".join(ATLAS_COLUMNS) + ") VALUES(" +
        ",".join([ph] * len(ATLAS_COLUMNS)) + ")",
        tuple(values[column] for column in ATLAS_COLUMNS),
    )
    return item_id


def insert_item(values: Mapping[str, Any]) -> str:
    with common_db.transaction() as (conn, kind):
        return insert_item_on_connection(conn, kind, values)


def update_item(item_id: str, changes: Mapping[str, Any], *, updated_at: str, updated_by: str) -> None:
    if not changes:
        return
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        assignments = [f"{column}={ph}" for column in changes]
        params = list(changes.values())
        assignments.extend([f"updated_at={ph}", f"updated_by={ph}"])
        params.extend([updated_at, updated_by, str(item_id)])
        conn.execute(
            f"UPDATE atlas_items SET {','.join(assignments)} WHERE id={ph}",
            tuple(params),
        )


def delete_item(item_id: str) -> None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"DELETE FROM atlas_items WHERE id={ph}",
            (str(item_id),),
        )
