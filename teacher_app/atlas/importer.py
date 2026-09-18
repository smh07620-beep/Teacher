"""Canonical Atlas DOCX import orchestration.

This module owns DOCX source lookup, preview parsing, embedded-image selection,
metadata merge and Atlas draft creation. HTTP/session handling remains in the
root compatibility adapter; image bytes are delegated to ``image_store``.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping

from teacher_app.atlas import image_store, service
from teacher_app.common.errors import ApiError
from teacher_app.materials import repository as material_repository


PREVIEW_WARNING = (
    "只會匯入可驗證的內嵌圖片；浮動圖、SmartArt、圖表、群組物件、OLE 與損壞 relationship 不會自動建立圖譜。"
)
EMPTY_IMPORT_WARNING = "請確認 DOCX 使用支援的 inline JPG/PNG/WEBP 圖片。"


def docx_source(
    material_id: str,
    uploaded_slides_dir,
    *,
    legacy_material_getter: Callable[[str], Mapping[str, Any] | None] | None = None,
) -> tuple[dict | None, Path | None]:
    """Resolve DOCX source through canonical materials, with isolated legacy fallback."""
    material = material_repository.get_material(material_id)
    if not material and legacy_material_getter is not None:
        legacy_material = legacy_material_getter(material_id)
        material = dict(legacy_material) if legacy_material else None
    if not material:
        return None, None
    path = (
        Path(uploaded_slides_dir)
        / str(material.get("folder") or material_id)
        / str(material.get("storageFilename") or material.get("filename") or "")
    )
    if path.suffix.lower() != ".docx" or not path.is_file():
        return material, None
    return material, path


def preview_docx_atlas(path: Path) -> dict:
    """Preserve the established DOCX Atlas preview projection."""
    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8", "ignore")
    text = " ".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", document_xml))
    images = []
    for index, relation_number in enumerate(
        re.findall(r'(?:embed|link)="rId(\d+)"', document_xml),
        1,
    ):
        images.append({
            "index": index,
            "relationshipId": "rId" + relation_number,
            "section": text[:180],
            "caption": "",
            "region": {"x": 0, "y": 0, "width": 1, "height": 1},
        })
    return {
        "images": images,
        "warnings": [
            "DOCX 預覽僅處理 inline/table 圖片；浮動圖、群組、SmartArt、圖表與 OLE 保留原文件，需人工處理。"
        ] if not images else [],
    }


def preview_import(
    user: Mapping[str, Any],
    material_id: str,
    uploaded_slides_dir,
    *,
    legacy_material_getter: Callable[[str], Mapping[str, Any] | None] | None = None,
) -> dict:
    material, path = docx_source(
        material_id,
        uploaded_slides_dir,
        legacy_material_getter=legacy_material_getter,
    )
    if not material or not path:
        raise ApiError(
            "ATLAS_DOCX_SOURCE_UNAVAILABLE",
            "需要可安全存取的 DOCX 原始檔。",
            status=409,
        )
    group = str(material.get("group") or material.get("groupKey") or "")
    if not service.can_manage(user, group):
        raise ApiError("ATLAS_DOCX_FORBIDDEN", "無權管理此教材。", status=403)
    preview = preview_docx_atlas(path)
    preview["warnings"] = list(preview.get("warnings") or []) + [PREVIEW_WARNING]
    return {
        "materialId": material_id,
        "preview": preview,
        "defaultGroup": group,
        "initialStatus": "draft",
    }


def confirm_import(
    user: Mapping[str, Any],
    material_id: str,
    body: Mapping[str, Any],
    *,
    uploaded_slides_dir,
    material_storage,
    legacy_material_getter: Callable[[str], Mapping[str, Any] | None] | None = None,
) -> dict:
    material, path = docx_source(
        material_id,
        uploaded_slides_dir,
        legacy_material_getter=legacy_material_getter,
    )
    if not material or not path:
        raise ApiError(
            "ATLAS_DOCX_SOURCE_UNAVAILABLE",
            "需要可安全存取的 DOCX 原始檔。",
            status=409,
        )
    source_group = str(material.get("group") or material.get("groupKey") or "")
    if not service.can_manage(user, source_group):
        raise ApiError("ATLAS_DOCX_FORBIDDEN", "無權管理此教材。", status=403)

    selected = body.get("items")
    if not isinstance(selected, list) or not selected:
        raise ApiError("ATLAS_DOCX_ITEMS_REQUIRED", "請至少選擇一張圖片。", status=400)
    common = body.get("metadata") or body.get("commonMetadata") or {}
    if not isinstance(common, dict):
        raise ApiError("ATLAS_DOCX_METADATA_INVALID", "共用 metadata 格式不正確。", status=400)

    created: list[str] = []
    with zipfile.ZipFile(path) as archive:
        media = [name for name in archive.namelist() if name.startswith("word/media/")]
        for picked in selected[:30]:
            if not isinstance(picked, dict):
                continue
            values = {**common, **picked}
            try:
                index = int(values.get("index", 0)) - 1
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= len(media):
                continue

            raw = archive.read(media[index])
            try:
                stored = image_store.store_image_bytes(
                    material_storage,
                    raw,
                    Path(media[index]).suffix,
                    max_bytes=None,
                )
            except image_store.AtlasImageError:
                continue

            group = str(values.get("group") or source_group).strip()
            if not group or not service.can_manage(user, group):
                continue
            category = str(values.get("category") or "microscope")
            if category not in service.ATLAS_CATEGORIES:
                category = "microscope"
            title = str(values.get("title") or Path(media[index]).stem)[:255]
            item_id = service.create_item(user, {
                "group": group,
                "category": category,
                "title": title,
                "imageUrl": stored["imageUrl"],
                "description": str(values.get("description") or "")[:6000],
                "tags": values.get("tags"),
                "differentialPoints": str(values.get("differentialPoints") or "")[:6000],
                "teachingNotes": str(values.get("teachingNotes") or "")[:6000],
                "difficulty": str(values.get("difficulty") or "general")[:40],
                "published": False,
                "source": "docx",
                "sourceMaterialId": material_id,
                "sourceDocx": str(material.get("filename") or "")[:255],
                "sortOrder": int(values.get("sortOrder") or 0),
                "annotationJson": {},
            })
            created.append(item_id)

    if not created:
        raise ApiError(
            "ATLAS_DOCX_NO_SAFE_IMAGES",
            "沒有可安全匯入的內嵌圖片。",
            status=409,
            extra={"warnings": [EMPTY_IMPORT_WARNING]},
        )
    return {"ok": True, "created": created, "status": "draft"}
