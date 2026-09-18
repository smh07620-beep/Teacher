"""Canonical material catalog and metadata behavior for Stage 5.1.

Cloud/object-storage engines remain compatibility services on ``app.py``.  This
module owns catalog projection, metadata validation/persistence and deletion
orchestration without importing provider credentials or SDK clients.
"""
from __future__ import annotations

import json
import re
import shutil
from typing import Any, Mapping

from teacher_app.common.errors import ApiError
from teacher_app.materials import repository


MATERIAL_TYPES = {"standard", "atlas", "infographic", "video", "troubleshooting", "sop", "case"}


def _fail(code: str, message: str, status: int = 400) -> ApiError:
    return ApiError(code, message, status=status)


def list_materials(base, requested_area: str) -> list[dict]:
    area_filter = base.normalize_area(requested_area or base.DEFAULT_TRAINING_AREA)
    labels = base.category_label_map()
    builtin: list[dict] = []
    for material in base.load_meta():
        if not material.get("isBuiltin"):
            continue
        group = base.normalize_group(material.get("group", base.DEFAULT_GROUP))
        area = base.normalize_area(material.get("area", base.DEFAULT_TRAINING_AREA))
        if area != area_filter:
            continue
        category = material.get("category", "")
        builtin.append(
            {
                **material,
                "group": group,
                "area": area,
                "viewerMode": "slides",
                "categoryLabel": labels.get(category, base.CATEGORY_LABELS.get(category, base.CATEGORY_LABELS[""])),
                "imageFolder": f"slides/{material['folder']}",
                "viewUrl": "",
            }
        )
    uploaded: list[dict] = []
    for material in repository.list_uploaded_materials(base, False):
        if material.get("area") != area_filter:
            continue
        category = material.get("category", "")
        uploaded.append(
            {
                **material,
                "categoryLabel": labels.get(category, base.CATEGORY_LABELS.get(category, base.CATEGORY_LABELS[""])),
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


def list_admin_materials(base) -> list[dict]:
    labels = base.category_label_map()
    items: list[dict] = []
    for material in base.load_meta():
        if material.get("isBuiltin"):
            group = base.normalize_group(material.get("group", base.DEFAULT_GROUP))
            category = material.get("category", "")
            items.append(
                {
                    **material,
                    "group": group,
                    "categoryLabel": labels.get(category, base.CATEGORY_LABELS.get(category, base.CATEGORY_LABELS[""])),
                }
            )
    for material in repository.list_uploaded_materials(base, True):
        category = material.get("category", "")
        items.append(
            {
                **material,
                "categoryLabel": labels.get(category, base.CATEGORY_LABELS.get(category, base.CATEGORY_LABELS[""])),
            }
        )
    return items


def update_material(base, material_id: str, data: Mapping[str, Any]) -> dict:
    entry = repository.get_material(base, material_id)
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
    group = base.normalize_group(str(data.get("group", entry.get("group", base.DEFAULT_GROUP))))
    area = base.normalize_area(str(data.get("area", entry.get("area", base.DEFAULT_TRAINING_AREA))))
    category = str(data.get("category", entry.get("category", "")))
    course_id = str(data.get("courseId", entry.get("courseId", ""))).strip()
    course = base.get_course(course_id) if course_id else None
    if not course or course.get("group") != group or course.get("area") != area:
        course_id = ""
    active = bool(data.get("active", entry.get("active", True)))
    quiz_category = base.get_quiz_category(category) if category else None
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
    entry = repository.get_material(base, material_id)
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
