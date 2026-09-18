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
