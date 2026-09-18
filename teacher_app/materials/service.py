"""Canonical material catalog, metadata behavior and deletion orchestration.

Ordinary material catalog/validation rules are independent from the legacy
Flask host. Cloud/object-storage deletion remains a temporary provider seam
until storage providers move under ``teacher_app.storage``.
"""
from __future__ import annotations

import json
import re
import shutil
from typing import Any, Mapping

from teacher_app.assessments import repository as assessment_repository
from teacher_app.common import scope
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.materials import catalog, repository


MATERIAL_TYPES = {"standard", "atlas", "infographic", "video", "troubleshooting", "sop", "case"}


def _fail(code: str, message: str, status: int = 400) -> ApiError:
    return ApiError(code, message, status=status)


def _category_labels() -> dict[str, str]:
    labels = dict(catalog.CATEGORY_LABELS)
    try:
        for category_id, title in assessment_repository.category_labels().items():
            labels[category_id] = title or labels.get(category_id, catalog.CATEGORY_LABELS[""])
    except Exception:
        # Material catalog remains usable if assessment labels are temporarily unavailable.
        pass
    return labels


def list_materials(_legacy_base, requested_area: str) -> list[dict]:
    area_filter = scope.normalize_area(requested_area or scope.DEFAULT_TRAINING_AREA)
    labels = _category_labels()
    builtin: list[dict] = []
    for material in catalog.load_builtin_meta():
        if not material.get("isBuiltin"):
            continue
        group = scope.normalize_group(material.get("group", scope.DEFAULT_GROUP))
        area = scope.normalize_area(material.get("area", scope.DEFAULT_TRAINING_AREA))
        if area != area_filter:
            continue
        category = material.get("category", "")
        builtin.append(
            {
                **material,
                "group": group,
                "area": area,
                "viewerMode": "slides",
                "categoryLabel": labels.get(category, catalog.CATEGORY_LABELS.get(category, catalog.CATEGORY_LABELS[""])),
                "imageFolder": f"slides/{material['folder']}",
                "viewUrl": "",
            }
        )
    uploaded: list[dict] = []
    for material in repository.list_uploaded_materials(include_inactive=False):
        if material.get("area") != area_filter:
            continue
        category = material.get("category", "")
        uploaded.append(
            {
                **material,
                "categoryLabel": labels.get(category, catalog.CATEGORY_LABELS.get(category, catalog.CATEGORY_LABELS[""])),
                "imageFolder": f"uploaded-slides/{material['folder']}",
                "previewUrl": (
                    f"/material-preview/{material['id']}"
                    if material.get("viewerMode") == "preview_pdf"
                    else material.get("previewUrl", "")
                ),
                "viewUrl": (
                    f"/view/{material['id']}"
                    if material.get("viewerMode") not in {"slides", "preview_pdf"}
                    else ""
                ),
            }
        )
    return builtin + uploaded


def list_admin_materials(_legacy_base) -> list[dict]:
    labels = _category_labels()
    items: list[dict] = []
    for material in catalog.load_builtin_meta():
        if material.get("isBuiltin"):
            group = scope.normalize_group(material.get("group", scope.DEFAULT_GROUP))
            category = material.get("category", "")
            items.append(
                {
                    **material,
                    "group": group,
                    "categoryLabel": labels.get(category, catalog.CATEGORY_LABELS.get(category, catalog.CATEGORY_LABELS[""])),
                }
            )
    for material in repository.list_uploaded_materials(include_inactive=True):
        category = material.get("category", "")
        items.append(
            {
                **material,
                "categoryLabel": labels.get(category, catalog.CATEGORY_LABELS.get(category, catalog.CATEGORY_LABELS[""])),
            }
        )
    return items


def update_material(_legacy_base, material_id: str, data: Mapping[str, Any]) -> dict:
    entry = repository.get_material(material_id)
    if not entry:
        raise _fail("MATERIAL_NOT_FOUND", "找不到可編輯的上傳教材", 404)
    title = str(data.get("title", entry["title"])).strip()[:255]
    desc = str(data.get("desc", entry.get("desc", ""))).strip()[:1000]
    material_type = str(data.get("materialType", entry.get("materialType", "standard"))).strip().lower()
    if material_type not in MATERIAL_TYPES:
        material_type = "standard"
    atlas_meta = data.get("atlasMeta", entry.get("atlasMeta", {}))
    if not isinstance(atlas_meta, dict):
        atlas_meta = {}
    atlas_meta = (
        {
            key: str(atlas_meta.get(key, "")).strip()[:1000]
            for key in ("category", "magnification", "interpretation", "clinical", "differential", "normality", "tags")
        }
        if material_type == "atlas"
        else {}
    )
    group = scope.normalize_group(str(data.get("group", entry.get("group", scope.DEFAULT_GROUP))))
    area = scope.normalize_area(str(data.get("area", entry.get("area", scope.DEFAULT_TRAINING_AREA))))
    category = str(data.get("category", entry.get("category", "")))
    course_id = str(data.get("courseId", entry.get("courseId", ""))).strip()
    course = course_repository.get_course(course_id) if course_id else None
    if not course or course.get("group") != group or course.get("area") != area:
        course_id = ""
    active = bool(data.get("active", entry.get("active", True)))
    quiz_category = assessment_repository.get_category(category) if category else None
    if category and (
        not quiz_category
        or quiz_category["group"] != group
        or quiz_category.get("area") != area
    ):
        category = ""
    repository.update_material_metadata(
        material_id,
        title=title,
        description=desc,
        category=category,
        group_key=group,
        training_area=area,
        course_id=course_id,
        material_type=material_type,
        atlas_meta_json=json.dumps(atlas_meta, ensure_ascii=False),
        active=active,
    )
    return {"ok": True}


def delete_material(base, material_id: str) -> dict:
    """Delete storage object + row; provider seam remains legacy until storage convergence."""
    entry = repository.get_material(material_id)
    if not entry:
        raise _fail("MATERIAL_NOT_FOUND", "內建教材不能從後台刪除，或找不到此教材", 404)

    backend = entry.get("storageBackend")
    if backend == "gdrive":
        try:
            base.gdrive_delete_material(entry)
        except Exception as exc:
            raise _fail("GDRIVE_DELETE_FAILED", f"Google Drive 教材刪除失敗：{exc}", 502) from exc
    elif backend == "mega":
        base.mega_destroy((entry.get("storageMeta") or {}).get("folderId", ""))
    elif backend == "oci":
        try:
            base.oci_delete_prefix(f"materials/{entry['id']}/")
        except Exception as exc:
            raise _fail("OCI_DELETE_FAILED", f"Oracle Object Storage 教材刪除失敗：{exc}", 502) from exc
    elif backend == "r2":
        try:
            base.r2_delete_prefix(f"materials/{entry['id']}/")
        except Exception as exc:
            raise _fail("R2_DELETE_FAILED", f"R2 教材刪除失敗：{exc}", 502) from exc
    else:
        shutil.rmtree(base.UPLOAD_DIR / entry["id"], ignore_errors=True)
        shutil.rmtree(base.UPLOADED_SLIDES_DIR / entry["folder"], ignore_errors=True)

    try:
        cache_file = base.PREVIEW_CACHE_DIR / (re.sub(r"[^A-Za-z0-9_-]", "_", str(material_id)) + ".pdf")
        if cache_file.exists():
            cache_file.unlink()
    except OSError:
        pass

    repository.delete_material_record(material_id)
    return {"ok": True}
