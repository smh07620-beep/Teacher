"""Canonical Worker-result validation and material persistence."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from teacher_app.common import scope
from teacher_app.materials import repository as material_repository


_OFFICE_EXTENSIONS = {
    ".pptx",
    ".ppt",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".odp",
    ".odt",
    ".ods",
    ".pdf",
}


def commit(job: dict, result: dict) -> dict:
    """Persist a Worker-produced material only after Web ownership validation."""
    payload = dict(job.get("payload") or {})
    material_id = str(job.get("materialId") or payload.get("materialId") or "")
    if not material_id:
        raise ValueError("背景工作缺少 materialId。")
    existing = material_repository.get_material(material_id)
    if existing:
        return existing
    backend = str(result.get("storageBackend") or "").lower()
    if backend not in {"mega", "gdrive", "r2", "oci", "local"}:
        raise ValueError("Worker 回報的儲存後端不合法。")
    storage_key = str(result.get("storageKey") or "")[:1000]
    if backend != "local" and not storage_key:
        raise ValueError("Worker 回報缺少正式教材儲存位置。")
    original = Path(
        payload.get("originalName") or job.get("originalName") or "untitled"
    ).name
    source_name = Path(
        str(result.get("storageFilename") or f"source{Path(original).suffix.lower()}")
    ).name
    try:
        page_count = max(0, min(10000, int(result.get("pageCount", 0) or 0)))
    except (TypeError, ValueError):
        page_count = 0
    storage_meta = (
        result.get("storageMeta") if isinstance(result.get("storageMeta"), dict) else {}
    )
    if Path(original).suffix.lower() in _OFFICE_EXTENSIONS:
        if page_count <= 0 or storage_meta.get("previewMode") != "single_pdf":
            raise ValueError("Office/PDF 必須有有效 preview.pdf 與 pageCount 才能完成。")

    # The Worker is trusted for conversion output, not for authorization scope.
    # Persist only the group/area captured and validated by the Web enqueue path;
    # malformed or stale payload scope must fail instead of silently becoming
    # grpBio/internal.
    group_key = scope.validate_group(
        payload.get("group"),
        default=scope.DEFAULT_GROUP,
    )
    training_area = scope.validate_area(
        payload.get("area"),
        default=scope.DEFAULT_TRAINING_AREA,
    )
    entry = {
        "id": material_id,
        "filename": original,
        "title": str(payload.get("title") or original)[:255],
        "description": str(
            payload.get("desc") or "管理者上傳之教育訓練補充教材"
        )[:1000],
        "category": str(payload.get("category") or "")[:100],
        "group_key": group_key,
        "training_area": training_area,
        "course_id": str(payload.get("courseId") or "")[:100],
        "folder": material_id,
        "page_count": page_count,
        "date_added": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "storage_filename": source_name,
        "storage_backend": backend,
        "storage_key": storage_key,
        "slides_prefix": str(result.get("slidesPrefix") or "")[:1000],
        "storage_meta": json.dumps(storage_meta, ensure_ascii=False),
        "material_type": str(payload.get("materialType") or "standard")[:40],
        "atlas_meta": json.dumps(
            result.get("atlasMeta") if isinstance(result.get("atlasMeta"), dict) else {},
            ensure_ascii=False,
        ),
        "active": True,
    }
    material_repository.insert_material(entry, ignore_conflict=True)
    return material_repository.get_material(material_id) or entry


__all__ = ["commit"]