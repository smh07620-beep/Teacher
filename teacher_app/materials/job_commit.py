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



def _sanitize_conversion_warnings(storage_meta: dict) -> dict:
    """Keep Worker-supplied conversion warnings small, typed and display-safe."""
    raw = storage_meta.get("conversionWarnings")
    if raw is None:
        return storage_meta
    cleaned = []
    if isinstance(raw, list):
        for item in raw[:6]:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()[:40]
            message = str(item.get("message") or "").strip()[:300]
            if code and message:
                cleaned.append({"code": code, "message": message})
    result = {key: value for key, value in storage_meta.items() if key != "conversionWarnings"}
    if cleaned:
        result["conversionWarnings"] = cleaned
    return result

def commit(job: dict, result: dict) -> dict:
    """Persist a Worker-produced material only after Web ownership validation."""
    payload = dict(job.get("payload") or {})
    material_id = str(job.get("materialId") or payload.get("materialId") or "")
    if not material_id:
        raise ValueError("背景工作缺少 materialId。")
    existing = material_repository.get_material(material_id)
    if existing:
        return existing
    target_material_id = str(payload.get("targetMaterialId") or "").strip()
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
    storage_meta = _sanitize_conversion_warnings(storage_meta)
    if Path(original).suffix.lower() in _OFFICE_EXTENSIONS:
        preview_mode = str(storage_meta.get("previewMode") or "").strip().lower()
        slides_prefix = str(result.get("slidesPrefix") or "").strip()
        slide_format = str(storage_meta.get("slideFormat") or "").strip().lower()
        has_single_preview = page_count > 0 and preview_mode == "single_pdf"
        has_paginated_preview = (
            page_count > 0
            and bool(slides_prefix)
            and slide_format in {"webp", "png", "jpg", "jpeg"}
        )
        if not (has_single_preview or has_paginated_preview):
            raise ValueError(
                "Office/PDF 必須有有效 preview.pdf，或完整的分頁預覽與 pageCount 才能完成。"
            )

    # Media can be normalized by the local Worker (for example microphone-only
    # WebM -> M4A). Keep the human base name while persisting the normalized
    # suffix so the canonical material viewer selects the correct player.
    display_filename = original
    media_kind = str(storage_meta.get("mediaKind") or "").strip().lower()
    normalized_suffix = Path(source_name).suffix.lower()
    if media_kind in {"audio", "video"} and normalized_suffix:
        display_filename = Path(original).with_suffix(normalized_suffix).name

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
    resolved_material_type=str(result.get("materialType") or payload.get("materialType") or "standard").strip().lower()
    if resolved_material_type not in material_repository.MATERIAL_TYPES:
        resolved_material_type="standard"
    if bool(payload.get("authoringOnly", False)):
        # 臨時私人來源：保留標記，供 24 小時清理明確辨識。
        storage_meta={**storage_meta,"authoringOnly":True}
    classification_method=str(result.get("classificationMethod") or "").strip()[:120]
    classification_reason=str(result.get("classificationReason") or "").strip()[:240]
    if classification_method or classification_reason:
        storage_meta={
            **storage_meta,
            "materialClassification":{
                "requested":str(payload.get("materialType") or "standard").strip().lower(),
                "resolved":resolved_material_type,
                "method":classification_method,
                "reason":classification_reason,
            },
        }

    entry = {
        "id": material_id,
        "filename": display_filename,
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
        "material_type": resolved_material_type,
        "atlas_meta": json.dumps(
            result.get("atlasMeta") if isinstance(result.get("atlasMeta"), dict) else {},
            ensure_ascii=False,
        ),
        # Private AI authoring inputs must never become learner-visible merely
        # because the Worker finished converting them.  The Web enqueue path
        # captures this flag; publication is a separate explicit teacher action.
        "active": not bool(payload.get("authoringOnly", False)),
    }
    if target_material_id:
        target = material_repository.get_material(target_material_id)
        if not target:
            raise ValueError("指定要更新版本的教材不存在。")
        if target.get("group") != group_key or target.get("area") != training_area:
            raise ValueError("新版教材的組別／訓練區域與原教材不一致。")
        reason = str(payload.get("versionChangeReason") or "").strip()[:1000]
        if not reason:
            raise ValueError("建立教材新版時必須提供版本變更原因。")
        requires_retraining = payload.get("requiresRetraining", False)
        if type(requires_retraining) is not bool:
            raise ValueError("教材新版的重新訓練設定格式不正確。")
        published_by = str(payload.get("uploadActor") or "system:worker").strip()[:100]
        updated = material_repository.replace_material_content_and_publish(
            target_material_id,
            content=entry,
            published_by=published_by or "system:worker",
            change_reason=reason,
            requires_retraining=requires_retraining,
        )
        if not updated:
            raise ValueError("指定要更新版本的教材不存在。")
        return updated

    material_repository.insert_material(entry, ignore_conflict=True)
    return material_repository.get_material(material_id) or entry


__all__ = ["commit"]
