"""Canonical material read repository.

SQL and row projection for uploaded-material reads live here.  Provider
credentials and storage SDK client construction remain outside this module.
"""
from __future__ import annotations

import json
from pathlib import Path

from teacher_app.common import db as common_db


MATERIAL_TYPES = {
    "standard",
    "atlas",
    "infographic",
    "video",
    "troubleshooting",
    "sop",
    "case",
}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def material_row_to_dict(base, row) -> dict:
    """Project a DB row to the stable legacy material response contract."""
    r = dict(row)
    r["isBuiltin"] = False
    r["is_builtin"] = False
    r["desc"] = r.pop("description", "")
    r["dateAdded"] = r.pop("date_added", "")
    r["pageCount"] = int(r.pop("page_count", 0) or 0)
    r["storageFilename"] = r.pop("storage_filename", "")
    r["storageBackend"] = (r.pop("storage_backend", "local") or "local").lower()
    r["storageKey"] = r.pop("storage_key", "") or ""
    r["slidesPrefix"] = r.pop("slides_prefix", "") or ""

    raw_storage_meta = r.pop("storage_meta", "{}") or "{}"
    try:
        r["storageMeta"] = json.loads(raw_storage_meta) if isinstance(raw_storage_meta, str) else (raw_storage_meta or {})
    except Exception:
        r["storageMeta"] = {}

    r["slideFormat"] = str((r["storageMeta"] or {}).get("slideFormat", "png") or "png").lower()
    material_type = str(r.pop("material_type", "standard") or "standard").lower()
    r["materialType"] = material_type if material_type in MATERIAL_TYPES else "standard"

    raw_atlas_meta = r.pop("atlas_meta", "{}") or "{}"
    try:
        r["atlasMeta"] = json.loads(raw_atlas_meta) if isinstance(raw_atlas_meta, str) else (raw_atlas_meta or {})
    except Exception:
        r["atlasMeta"] = {}

    r["active"] = bool(r.get("active", True))
    r["blindMode"] = bool(r.pop("blind_mode", False))
    r["group"] = base.normalize_group(r.pop("group_key", base.DEFAULT_GROUP))
    r["area"] = base.normalize_area(r.pop("training_area", base.DEFAULT_TRAINING_AREA))
    r["courseId"] = r.pop("course_id", "") or ""

    ext = Path(r.get("filename", "")).suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        r["viewerMode"] = "video"
    elif ext in AUDIO_EXTENSIONS:
        r["viewerMode"] = "audio"
    elif ext in IMAGE_EXTENSIONS:
        r["viewerMode"] = "image"
    elif (r.get("storageMeta") or {}).get("previewMode") == "single_pdf":
        r["viewerMode"] = "preview_pdf"
    elif r["pageCount"] > 0:
        r["viewerMode"] = "slides"
    else:
        r["viewerMode"] = "download"

    r["previewUrl"] = f"/material-preview/{r.get('id', '')}" if r["viewerMode"] == "preview_pdf" else ""
    return r


def list_uploaded_materials(base, include_inactive: bool = False) -> list[dict]:
    """Read uploaded materials using the shared pooled connection path."""
    with common_db.read_connection() as (conn, kind):
        sql = "SELECT * FROM materials"
        if not include_inactive:
            sql += " WHERE active = " + ("TRUE" if kind == "postgres" else "1")
        sql += " ORDER BY date_added DESC"
        rows = conn.execute(sql).fetchall()
    return [material_row_to_dict(base, row) for row in rows]


def get_material(base, material_id: str) -> dict | None:
    """Read one material using the shared pooled connection path."""
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM materials WHERE id = {ph}", (material_id,)).fetchone()
    return material_row_to_dict(base, row) if row else None


MATERIAL_DB_COLUMNS = (
    "id", "filename", "title", "description", "category", "group_key",
    "training_area", "course_id", "folder", "page_count", "date_added",
    "storage_filename", "storage_backend", "storage_key", "slides_prefix",
    "storage_meta", "material_type", "atlas_meta", "active",
)


def insert_material_on_connection(
    conn,
    kind: str,
    entry: dict,
    *,
    ignore_conflict: bool = False,
) -> None:
    """Insert one material using a caller-owned transaction."""
    ph = common_db.placeholder(kind)
    columns = ",".join(MATERIAL_DB_COLUMNS)
    marks = ",".join([ph] * len(MATERIAL_DB_COLUMNS))
    values = tuple(
        (bool(entry.get(name)) if name == "active" and kind == "postgres" else
         int(bool(entry.get(name))) if name == "active" else entry.get(name))
        for name in MATERIAL_DB_COLUMNS
    )
    if kind == "sqlite" and ignore_conflict:
        sql = f"INSERT OR IGNORE INTO materials ({columns}) VALUES ({marks})"
    else:
        sql = f"INSERT INTO materials ({columns}) VALUES ({marks})"
        if kind == "postgres" and ignore_conflict:
            sql += " ON CONFLICT(id) DO NOTHING"
    conn.execute(sql, values)


def insert_material(entry: dict, *, ignore_conflict: bool = False) -> None:
    """Insert one material inside an explicit transaction."""
    with common_db.transaction() as (conn, kind):
        insert_material_on_connection(
            conn,
            kind,
            entry,
            ignore_conflict=ignore_conflict,
        )


def update_material_storage(
    material_id: str,
    *,
    backend: str,
    storage_key: str,
    slides_prefix: str,
    storage_meta_json: str | None = None,
) -> None:
    """Update material storage pointers inside an explicit transaction."""
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        if storage_meta_json is None:
            conn.execute(
                f"UPDATE materials SET storage_backend={ph}, storage_key={ph}, slides_prefix={ph} WHERE id={ph}",
                (backend, storage_key, slides_prefix, material_id),
            )
        else:
            conn.execute(
                f"UPDATE materials SET storage_backend={ph}, storage_key={ph}, slides_prefix={ph}, storage_meta={ph} WHERE id={ph}",
                (backend, storage_key, slides_prefix, storage_meta_json, material_id),
            )


def update_material_metadata(
    material_id: str,
    *,
    title: str,
    description: str,
    category: str,
    group_key: str,
    training_area: str,
    course_id: str,
    material_type: str,
    atlas_meta_json: str,
    active: bool,
) -> None:
    """Persist editable material metadata in one explicit transaction."""
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            "UPDATE materials SET "
            f"title={ph}, description={ph}, category={ph}, group_key={ph}, "
            f"training_area={ph}, course_id={ph}, material_type={ph}, "
            f"atlas_meta={ph}, active={ph} WHERE id={ph}",
            (
                title, description, category, group_key, training_area,
                course_id, material_type, atlas_meta_json,
                active if kind == "postgres" else int(active), material_id,
            ),
        )


def delete_material_record(material_id: str) -> None:
    """Delete one material row in an explicit transaction."""
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(f"DELETE FROM materials WHERE id={ph}", (material_id,))


def clear_course_assignment(conn, kind: str, course_id: str) -> None:
    """Clear one course link using the caller-owned transaction."""
    ph = common_db.placeholder(kind)
    conn.execute(f"UPDATE materials SET course_id='' WHERE course_id={ph}", (course_id,))


def material_ids_for_course(conn, kind: str, course_id: str) -> set[str]:
    """Read material ids inside the caller-owned course transaction."""
    ph = common_db.placeholder(kind)
    rows = conn.execute(f"SELECT id FROM materials WHERE course_id={ph}", (course_id,)).fetchall()
    return {str(dict(row).get("id") or "") for row in rows if dict(row).get("id")}


def replace_category_assignments(
    category_id: str,
    material_ids: list[str],
    *,
    group_key: str,
    training_area: str,
) -> None:
    """Replace assessment-material links in one explicit transaction."""
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(f"UPDATE materials SET category='' WHERE category={ph}", (category_id,))
        if material_ids:
            placeholders = ",".join([ph] * len(material_ids))
            conn.execute(
                f"UPDATE materials SET category={ph} WHERE id IN ({placeholders}) "
                f"AND group_key={ph} AND training_area={ph}",
                tuple([category_id] + list(material_ids) + [group_key, training_area]),
            )


def clear_category_assignment(conn, kind: str, category_id: str) -> None:
    """Clear one assessment link using the caller-owned transaction."""
    ph = common_db.placeholder(kind)
    conn.execute(f"UPDATE materials SET category='' WHERE category={ph}", (category_id,))
