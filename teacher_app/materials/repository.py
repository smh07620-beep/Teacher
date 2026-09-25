"""Canonical material data access.

SQL and row projection for uploaded materials live here. Provider credentials
and storage SDK/process ownership remain outside this module.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from teacher_app.common import db as common_db
from teacher_app.common import scope


MATERIAL_TYPES = {"standard", "atlas", "infographic", "video", "troubleshooting", "sop", "case"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def material_row_to_dict(row_or_legacy_base, legacy_row=None) -> dict:
    """Project a DB row; the optional first legacy arg is ignored compatibility glue."""
    row = legacy_row if legacy_row is not None else row_or_legacy_base
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
    r["group"] = scope.normalize_group(r.pop("group_key", scope.DEFAULT_GROUP))
    r["area"] = scope.normalize_area(r.pop("training_area", scope.DEFAULT_TRAINING_AREA))
    r["courseId"] = r.pop("course_id", "") or ""
    r["currentVersion"] = max(1, int(r.pop("current_version", 1) or 1))
    r["requiredCompletionVersion"] = max(
        1,
        min(
            r["currentVersion"],
            int(r.pop("required_completion_version", 1) or 1),
        ),
    )
    r["versionUpdatedAt"] = str(r.pop("version_updated_at", "") or "")
    r["versionUpdatedBy"] = str(r.pop("version_updated_by", "") or "")
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


def list_uploaded_materials(legacy_base=None, include_inactive: bool = False) -> list[dict]:
    """Read uploaded materials; legacy_base is accepted but never consulted."""
    if isinstance(legacy_base, bool) and include_inactive is False:
        include_inactive = legacy_base
    with common_db.read_connection() as (conn, kind):
        sql = "SELECT * FROM materials"
        if not include_inactive:
            sql += " WHERE active = " + ("TRUE" if kind == "postgres" else "1")
        sql += " ORDER BY date_added DESC"
        rows = conn.execute(sql).fetchall()
    return [material_row_to_dict(row) for row in rows]


def get_material(material_or_legacy_base, legacy_material_id: str | None = None) -> dict | None:
    """Read one material; old (base, id) calls remain format-only compatibility."""
    material_id = legacy_material_id if legacy_material_id is not None else str(material_or_legacy_base or "")
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM materials WHERE id = {ph}", (material_id,)).fetchone()
    return material_row_to_dict(row) if row else None


MATERIAL_DB_COLUMNS = (
    "id", "filename", "title", "description", "category", "group_key",
    "training_area", "course_id", "folder", "page_count", "date_added",
    "storage_filename", "storage_backend", "storage_key", "slides_prefix",
    "storage_meta", "material_type", "atlas_meta", "active",
)


def _table_exists(conn, kind: str, table: str) -> bool:
    if kind == "postgres":
        return bool(
            conn.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=current_schema() AND table_name=%s",
                (table,),
            ).fetchone()
        )
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def ensure_material_version_baseline_on_connection(conn, kind: str, entry: dict) -> None:
    """Create immutable V1 history for materials created after migration 0084."""
    if not _table_exists(conn, kind, "material_versions"):
        return
    material_id = str(entry.get("id") or "").strip()
    if not material_id:
        return
    ph = common_db.placeholder(kind)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    conn.execute(
        f"UPDATE materials SET version_updated_at={ph},version_updated_by={ph} "
        f"WHERE id={ph} AND (version_updated_at='' OR version_updated_at IS NULL)",
        (now, "system:create", material_id),
    )
    snapshot = dict(entry)
    snapshot.update(
        {
            "current_version": 1,
            "required_completion_version": 1,
            "version_updated_at": now,
            "version_updated_by": "system:create",
        }
    )
    params = (
        material_id,
        1,
        False if kind == "postgres" else 0,
        "initial publication",
        now,
        "system:create",
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), default=str),
    )
    if kind == "postgres":
        conn.execute(
            "INSERT INTO material_versions "
            "(material_id,version,requires_retraining,change_reason,published_at,published_by,snapshot) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(material_id,version) DO NOTHING",
            params,
        )
    else:
        conn.execute(
            "INSERT OR IGNORE INTO material_versions "
            "(material_id,version,requires_retraining,change_reason,published_at,published_by,snapshot) "
            "VALUES (?,?,?,?,?,?,?)",
            params,
        )


def insert_material_on_connection(conn, kind: str, entry: dict, *, ignore_conflict: bool = False) -> None:
    ph = common_db.placeholder(kind)
    columns = ",".join(MATERIAL_DB_COLUMNS)
    marks = ",".join([ph] * len(MATERIAL_DB_COLUMNS))
    values = tuple((bool(entry.get(name)) if name == "active" and kind == "postgres" else int(bool(entry.get(name))) if name == "active" else entry.get(name)) for name in MATERIAL_DB_COLUMNS)
    if kind == "sqlite" and ignore_conflict:
        sql = f"INSERT OR IGNORE INTO materials ({columns}) VALUES ({marks})"
    else:
        sql = f"INSERT INTO materials ({columns}) VALUES ({marks})"
        if kind == "postgres" and ignore_conflict:
            sql += " ON CONFLICT(id) DO NOTHING"
    conn.execute(sql, values)
    ensure_material_version_baseline_on_connection(conn, kind, entry)


def insert_material(entry: dict, *, ignore_conflict: bool = False) -> None:
    with common_db.transaction() as (conn, kind):
        insert_material_on_connection(conn, kind, entry, ignore_conflict=ignore_conflict)


def update_material_storage(material_id: str, *, backend: str, storage_key: str, slides_prefix: str, storage_meta_json: str | None = None) -> None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        if storage_meta_json is None:
            conn.execute(f"UPDATE materials SET storage_backend={ph}, storage_key={ph}, slides_prefix={ph} WHERE id={ph}", (backend, storage_key, slides_prefix, material_id))
        else:
            conn.execute(f"UPDATE materials SET storage_backend={ph}, storage_key={ph}, slides_prefix={ph}, storage_meta={ph} WHERE id={ph}", (backend, storage_key, slides_prefix, storage_meta_json, material_id))


def update_material_metadata(material_id: str, *, title: str, description: str, category: str, group_key: str, training_area: str, course_id: str, material_type: str, atlas_meta_json: str, active: bool) -> None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            "UPDATE materials SET "
            f"title={ph}, description={ph}, category={ph}, group_key={ph}, training_area={ph}, course_id={ph}, material_type={ph}, atlas_meta={ph}, active={ph} WHERE id={ph}",
            (title, description, category, group_key, training_area, course_id, material_type, atlas_meta_json, active if kind == "postgres" else int(active), material_id),
        )


def material_version_row_to_dict(row) -> dict:
    item = dict(row)
    raw_snapshot = item.pop("snapshot", "{}") or "{}"
    try:
        snapshot = json.loads(raw_snapshot) if isinstance(raw_snapshot, str) else dict(raw_snapshot or {})
    except Exception:
        snapshot = {}
    return {
        "materialId": str(item.get("material_id") or ""),
        "version": max(1, int(item.get("version") or 1)),
        "requiresRetraining": bool(item.get("requires_retraining", False)),
        "changeReason": str(item.get("change_reason") or ""),
        "publishedAt": str(item.get("published_at") or ""),
        "publishedBy": str(item.get("published_by") or ""),
        "snapshot": snapshot,
    }


def list_material_versions(material_id: str) -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM material_versions WHERE material_id={ph} ORDER BY version DESC",
            (material_id,),
        ).fetchall()
    return [material_version_row_to_dict(row) for row in rows]


def publish_material_version(
    material_id: str,
    *,
    published_by: str,
    change_reason: str,
    requires_retraining: bool,
) -> dict | None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        select_sql = f"SELECT * FROM materials WHERE id={ph}"
        if kind == "postgres":
            select_sql += " FOR UPDATE"
        row = conn.execute(select_sql, (material_id,)).fetchone()
        if not row:
            return None
        current_row = dict(row)
        current_version = max(1, int(current_row.get("current_version", 1) or 1))
        new_version = current_version + 1
        required_version = max(
            1,
            int(current_row.get("required_completion_version", 1) or 1),
        )
        if requires_retraining:
            required_version = new_version
        conn.execute(
            f"UPDATE materials SET current_version={ph},required_completion_version={ph},"
            f"version_updated_at={ph},version_updated_by={ph} WHERE id={ph}",
            (new_version, required_version, now, published_by, material_id),
        )
        snapshot = dict(current_row)
        snapshot.update(
            {
                "current_version": new_version,
                "required_completion_version": required_version,
                "version_updated_at": now,
                "version_updated_by": published_by,
            }
        )
        params = (
            material_id,
            new_version,
            requires_retraining if kind == "postgres" else int(requires_retraining),
            change_reason,
            now,
            published_by,
            json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), default=str),
        )
        conn.execute(
            f"INSERT INTO material_versions "
            f"(material_id,version,requires_retraining,change_reason,published_at,published_by,snapshot) "
            f"VALUES ({','.join([ph] * 7)})",
            params,
        )
    return get_material(material_id)


def delete_material_record(material_id: str) -> None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(f"DELETE FROM materials WHERE id={ph}", (material_id,))


def clear_course_assignment(conn, kind: str, course_id: str) -> None:
    ph = common_db.placeholder(kind)
    conn.execute(f"UPDATE materials SET course_id='' WHERE course_id={ph}", (course_id,))


def material_ids_for_course(conn, kind: str, course_id: str) -> set[str]:
    ph = common_db.placeholder(kind)
    rows = conn.execute(f"SELECT id FROM materials WHERE course_id={ph}", (course_id,)).fetchall()
    return {str(dict(row).get("id") or "") for row in rows if dict(row).get("id")}


def replace_category_assignments(category_id: str, material_ids: list[str], *, group_key: str, training_area: str) -> None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(f"UPDATE materials SET category='' WHERE category={ph}", (category_id,))
        if material_ids:
            placeholders = ",".join([ph] * len(material_ids))
            conn.execute(f"UPDATE materials SET category={ph} WHERE id IN ({placeholders}) AND group_key={ph} AND training_area={ph}", tuple([category_id] + list(material_ids) + [group_key, training_area]))


def clear_category_assignment(conn, kind: str, category_id: str) -> None:
    ph = common_db.placeholder(kind)
    conn.execute(f"UPDATE materials SET category='' WHERE category={ph}", (category_id,))
