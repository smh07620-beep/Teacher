"""Canonical Atlas DOCX import orchestration.

This module owns DOCX source lookup, preview parsing, embedded-image selection,
metadata merge and Atlas draft creation. HTTP/session handling remains in the
root compatibility adapter; image bytes are delegated to ``image_store``.
"""
from __future__ import annotations

import posixpath
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping

from teacher_app.atlas import image_store, service
from teacher_app.assessments import ai_runtime
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



def materialize_docx_source(
    material_id: str,
    uploaded_slides_dir,
    *,
    paths_provider=None,
    legacy_material_getter: Callable[[str], Mapping[str, Any] | None] | None = None,
) -> tuple[dict | None, Path | None, Path | None]:
    """Resolve a DOCX source from either legacy local slides or shared storage.

    Modern materials normally live on R2/MEGA/GDrive rather than Render's local
    filesystem. Atlas import must therefore use the same canonical material
    source resolver as AI authoring instead of treating every remote DOCX as
    unavailable.
    """
    material, local = docx_source(
        material_id,
        uploaded_slides_dir,
        legacy_material_getter=legacy_material_getter,
    )
    if local:
        return material, local, None
    if not material or paths_provider is None:
        return material, None, None
    if Path(str(material.get("filename") or material.get("storageFilename") or "")).suffix.lower() != ".docx":
        return material, None, None
    temp_root = None
    try:
        temp_root, source = ai_runtime.material_source_to_temp(
            material,
            paths_provider=paths_provider,
        )
        if source.suffix.lower() != ".docx" or not source.is_file():
            shutil.rmtree(temp_root, ignore_errors=True)
            return material, None, None
        return material, source, temp_root
    except Exception as exc:
        if temp_root:
            shutil.rmtree(temp_root, ignore_errors=True)
        raise ApiError(
            "ATLAS_DOCX_SOURCE_FETCH_FAILED",
            f"DOCX 原始檔目前無法從共用儲存讀取：{exc}",
            status=409,
        ) from exc


_DOCX_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
}
_DOCX_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DOCX_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _atlas_category_hint(text: str) -> str:
    normalized = str(text or "").casefold()
    if any(token in normalized for token in ("血球", "紅血球", "白血球", "血液", "blood cell", "rbc", "wbc")):
        return "blood_cell"
    if any(token in normalized for token in ("尿沉渣", "尿液沉渣", "結晶", "cast", "urine")):
        return "urine_sediment"
    if any(token in normalized for token in ("菌落", "colony", "培養皿", "培養基")):
        return "colony"
    return "microscope"


def _docx_relationship_media(archive: zipfile.ZipFile) -> dict[str, str]:
    try:
        rel_root = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
    except (KeyError, ET.ParseError):
        return {}
    names = set(archive.namelist())
    resolved: dict[str, str] = {}
    for relation in rel_root.findall(f"{{{_DOCX_REL_NS}}}Relationship"):
        relation_id = str(relation.attrib.get("Id") or "").strip()
        target = str(relation.attrib.get("Target") or "").strip().replace("\\", "/")
        if not relation_id or not target or relation.attrib.get("TargetMode") == "External":
            continue
        candidate = posixpath.normpath(posixpath.join("word", target)).lstrip("/")
        if not candidate.startswith("word/media/"):
            continue
        if Path(candidate).suffix.lower() not in _DOCX_IMAGE_EXTENSIONS:
            continue
        if candidate in names:
            resolved[relation_id] = candidate
    return resolved


def _docx_inline_images(path: Path) -> list[dict]:
    """Return verified inline/table DOCX images in document order.

    The relationship id is resolved against document.xml.rels so confirm_import
    never guesses that word/media lexical order matches the visual document
    order.  This is important for clinical Atlas imports where a wrong image /
    caption pairing is unacceptable.
    """
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
        relationships = _docx_relationship_media(archive)

    paragraphs: list[tuple[str, list[str]]] = []
    relationship_attribute = f"{{{_DOCX_NS['r']}}}embed"
    link_attribute = f"{{{_DOCX_NS['r']}}}link"
    legacy_id_attribute = f"{{{_DOCX_NS['r']}}}id"
    for paragraph in root.findall(".//w:p", _DOCX_NS):
        parts = [
            node.text
            for node in paragraph.findall(".//w:t", _DOCX_NS)
            if node.text
        ]
        paragraph_text = re.sub(r"\s+", " ", "".join(parts)).strip()
        relation_ids: list[str] = []
        for image in paragraph.findall(".//a:blip", _DOCX_NS):
            relation_id = str(
                image.attrib.get(relationship_attribute)
                or image.attrib.get(link_attribute)
                or ""
            ).strip()
            if relation_id and relation_id in relationships:
                relation_ids.append(relation_id)
        for image in paragraph.findall(".//v:imagedata", _DOCX_NS):
            relation_id = str(image.attrib.get(legacy_id_attribute) or "").strip()
            if relation_id and relation_id in relationships:
                relation_ids.append(relation_id)
        paragraphs.append((paragraph_text, relation_ids))

    images: list[dict] = []
    seen_media: set[str] = set()
    for paragraph_index, (paragraph_text, relation_ids) in enumerate(paragraphs):
        nearby = " ".join(
            value
            for value, _refs in paragraphs[
                max(0, paragraph_index - 1): min(len(paragraphs), paragraph_index + 2)
            ]
            if value
        )
        section = re.sub(r"\s+", " ", nearby or paragraph_text).strip()[:300]
        for relation_id in relation_ids:
            media_path = relationships.get(relation_id, "")
            if not media_path or media_path in seen_media:
                continue
            seen_media.add(media_path)
            images.append({
                "index": len(images) + 1,
                "relationshipId": relation_id,
                "mediaPath": media_path,
                "fileName": Path(media_path).name,
                "section": section,
                "caption": paragraph_text[:180],
                "suggestedCategory": _atlas_category_hint(section),
                "region": {"x": 0, "y": 0, "width": 1, "height": 1},
            })
    return images


def preview_docx_atlas(path: Path) -> dict:
    """Preview verified embedded images that can become independent Atlas drafts."""
    try:
        images = _docx_inline_images(path)
    except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise ApiError(
            "ATLAS_DOCX_INVALID",
            f"DOCX 結構無法解析：{type(exc).__name__}",
            status=409,
        ) from exc
    warnings = []
    if not images:
        warnings.append(
            "沒有找到可安全抽出的 inline/table JPG、PNG 或 WEBP；浮動圖、SmartArt、圖表、群組物件與 OLE 不會自動建立圖譜。"
        )
    return {"images": images, "warnings": warnings}


def preview_import(
    user: Mapping[str, Any],
    material_id: str,
    uploaded_slides_dir,
    *,
    paths_provider=None,
    legacy_material_getter: Callable[[str], Mapping[str, Any] | None] | None = None,
) -> dict:
    material, path, cleanup_root = materialize_docx_source(
        material_id,
        uploaded_slides_dir,
        paths_provider=paths_provider,
        legacy_material_getter=legacy_material_getter,
    )
    try:
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
    finally:
        if cleanup_root:
            shutil.rmtree(cleanup_root, ignore_errors=True)


def confirm_import(
    user: Mapping[str, Any],
    material_id: str,
    body: Mapping[str, Any],
    *,
    uploaded_slides_dir,
    material_storage,
    paths_provider=None,
    legacy_material_getter: Callable[[str], Mapping[str, Any] | None] | None = None,
) -> dict:
    material, path, cleanup_root = materialize_docx_source(
        material_id,
        uploaded_slides_dir,
        paths_provider=paths_provider,
        legacy_material_getter=legacy_material_getter,
    )
    if not material or not path:
        if cleanup_root:
            shutil.rmtree(cleanup_root, ignore_errors=True)
        raise ApiError(
            "ATLAS_DOCX_SOURCE_UNAVAILABLE",
            "需要可安全存取的 DOCX 原始檔。",
            status=409,
        )
    source_group = str(material.get("group") or material.get("groupKey") or "")
    if not service.can_manage(user, source_group):
        if cleanup_root:
            shutil.rmtree(cleanup_root, ignore_errors=True)
        raise ApiError("ATLAS_DOCX_FORBIDDEN", "無權管理此教材。", status=403)

    selected = body.get("items")
    if not isinstance(selected, list) or not selected:
        if cleanup_root:
            shutil.rmtree(cleanup_root, ignore_errors=True)
        raise ApiError("ATLAS_DOCX_ITEMS_REQUIRED", "請至少選擇一張圖片。", status=400)
    common = body.get("metadata") or body.get("commonMetadata") or {}
    if not isinstance(common, dict):
        if cleanup_root:
            shutil.rmtree(cleanup_root, ignore_errors=True)
        raise ApiError("ATLAS_DOCX_METADATA_INVALID", "共用 metadata 格式不正確。", status=400)

    created: list[str] = []
    candidates = _docx_inline_images(path)
    by_index = {int(item["index"]): item for item in candidates}
    by_relationship = {
        str(item.get("relationshipId") or ""): item
        for item in candidates
        if item.get("relationshipId")
    }
    with zipfile.ZipFile(path) as archive:
        for picked in selected[:30]:
            if not isinstance(picked, dict):
                continue
            values = {**common, **picked}
            relation_id = str(values.get("relationshipId") or "").strip()
            candidate = by_relationship.get(relation_id) if relation_id else None
            if candidate is None:
                try:
                    candidate = by_index.get(int(values.get("index", 0)))
                except (TypeError, ValueError):
                    candidate = None
            if not candidate:
                continue
            media_path = str(candidate.get("mediaPath") or "")
            if not media_path:
                continue

            raw = archive.read(media_path)
            try:
                stored = image_store.store_image_bytes(
                    material_storage,
                    raw,
                    Path(media_path).suffix,
                    max_bytes=None,
                )
            except image_store.AtlasImageError:
                continue

            group = str(values.get("group") or source_group).strip()
            if not group or not service.can_manage(user, group):
                continue
            category = str(values.get("category") or candidate.get("suggestedCategory") or "microscope")
            if category not in service.ATLAS_CATEGORIES:
                category = "microscope"
            title = str(
                values.get("title")
                or candidate.get("caption")
                or Path(media_path).stem
            )[:255]
            item_id = service.create_item(user, {
                "group": group,
                "category": category,
                "title": title,
                "imageUrl": stored["imageUrl"],
                "description": str(values.get("description") or candidate.get("section") or "")[:6000],
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
        if cleanup_root:
            shutil.rmtree(cleanup_root, ignore_errors=True)
        raise ApiError(
            "ATLAS_DOCX_NO_SAFE_IMAGES",
            "沒有可安全匯入的內嵌圖片。",
            status=409,
            extra={"warnings": [EMPTY_IMPORT_WARNING]},
        )
    if cleanup_root:
        shutil.rmtree(cleanup_root, ignore_errors=True)
    return {"ok": True, "created": created, "status": "draft"}
