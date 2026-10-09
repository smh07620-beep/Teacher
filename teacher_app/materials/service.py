"""Canonical material catalog, metadata behavior and deletion orchestration.

Ordinary material catalog/validation rules are independent from the legacy
Flask host. Cloud/object-storage deletion remains a temporary provider seam
until storage providers move under ``teacher_app.storage``.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from teacher_app.assessments import repository as assessment_repository
from teacher_app.common import scope
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.materials import catalog, derivative_repository, repository
from teacher_app import storage as canonical_storage
from teacher_app.storage.web_runtime import WebStorageRuntime


LOGGER = logging.getLogger(__name__)

MATERIAL_TYPES = {"standard", "atlas", "infographic", "video", "troubleshooting", "sop", "case"}


def _fail(code: str, message: str, status: int = 400, **extra) -> ApiError:
    return ApiError(code, message, status=status, extra=extra or None)


def _category_labels() -> dict[str, str]:
    labels = dict(catalog.CATEGORY_LABELS)
    try:
        for category_id, title in assessment_repository.category_labels().items():
            labels[category_id] = title or labels.get(category_id, catalog.CATEGORY_LABELS[""])
    except Exception as exc:
        # Material catalog remains usable if assessment labels are temporarily unavailable.
        LOGGER.warning(
            "material category label lookup failed error_type=%s",
            type(exc).__name__,
        )
    return labels


def list_materials(base_or_area=None, requested_area: str | None = None) -> list[dict]:
    if requested_area is None:
        requested_area = str(base_or_area or scope.DEFAULT_TRAINING_AREA)
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
    return builtin + _attach_narrations(uploaded)


def _attach_narrations(uploaded: list[dict]) -> list[dict]:
    """Fold AI narration into its source material for learners.

    The narration stays a stored material row, but learners see one material
    with a ``narration`` companion (auto-played by the viewer) instead of a
    second, separate "AI 語音" entry.
    """
    by_id = {str(item.get("id")): item for item in uploaded}
    narrations: dict[str, dict] = {}
    folded: set[str] = set()
    for item in uploaded:
        meta = item.get("storageMeta") or {}
        source_id = str(meta.get("sourceMaterialId") or "")
        if meta.get("mediaKind") not in {"ai_narration", "teacher_narration"} or not source_id or source_id not in by_id:
            continue
        previous = narrations.get(source_id)
        if previous is None or str(item.get("dateAdded") or "") > str(previous.get("dateAdded") or ""):
            narrations[source_id] = item
        folded.add(str(item.get("id")))
    result = []
    for item in uploaded:
        item_id = str(item.get("id"))
        if item_id in folded:
            continue
        narration = narrations.get(item_id)
        if narration:
            narration_meta = narration.get("storageMeta") or {}
            payload = {
                "id": narration.get("id"),
                "title": narration.get("title") or "AI 配音",
                "viewUrl": f"/view/{narration['id']}",
            }
            if narration_meta.get("mediaKind") == "teacher_narration":
                # 老師自己錄的旁白：附上翻頁時間表，學員端可隨旁白自動翻頁。
                # 教材之後改版時時間表可能對不上頁面，標記 stale 讓前端只播聲音不翻頁。
                payload.update({
                    "kind": "teacher",
                    "title": narration.get("title") or "老師旁白",
                    "timeline": list(narration_meta.get("timeline") or []),
                    "durationMs": int(narration_meta.get("durationMs") or 0),
                    "stale": int(narration_meta.get("sourceVersion") or 1) != int(item.get("currentVersion") or 1),
                })
            item = {**item, "narration": payload}
        result.append(item)
    return result


def list_admin_materials(_legacy_base=None) -> list[dict]:
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


def update_material(base_or_material_id, material_id_or_data, data: Mapping[str, Any] | None = None) -> dict:
    if data is None:
        material_id = str(base_or_material_id)
        data = material_id_or_data
    else:
        material_id = str(material_id_or_data)
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


def list_material_versions(material_id: str) -> list[dict]:
    material_id = str(material_id or "").strip()
    if not repository.get_material(material_id):
        raise _fail("MATERIAL_NOT_FOUND", "找不到可管理的教材", 404)
    versions = repository.list_material_versions(material_id)
    derivatives = derivative_repository.list_for_material(material_id)
    by_version: dict[int, list[dict]] = {}
    for item in derivatives:
        by_version.setdefault(int(item.get("materialVersion") or 1), []).append(item)
    return [
        {
            **version,
            "derivatives": by_version.get(int(version.get("version") or 1), []),
        }
        for version in versions
    ]


def publish_material_version(
    material_id: str,
    data: Mapping[str, Any],
    *,
    actor_username: str,
) -> dict:
    material_id = str(material_id or "").strip()
    entry = repository.get_material(material_id)
    if not entry:
        raise _fail("MATERIAL_NOT_FOUND", "找不到可管理的教材", 404)
    if not isinstance(data, Mapping):
        raise _fail("MATERIAL_VERSION_PAYLOAD_INVALID", "版本資料格式不正確")
    reason = str(data.get("changeReason") or "").strip()[:1000]
    if not reason:
        raise _fail("MATERIAL_VERSION_REASON_REQUIRED", "請輸入本次版本變更原因")
    requires_retraining = data.get("requiresRetraining", False)
    if type(requires_retraining) is not bool:
        raise _fail("MATERIAL_VERSION_RETRAINING_INVALID", "重新訓練設定格式不正確")
    actor_username = str(actor_username or "").strip()[:100]
    if not actor_username:
        raise _fail("MATERIAL_VERSION_ACTOR_REQUIRED", "無法確認版本發布者", 401)
    updated = repository.publish_material_version(
        material_id,
        published_by=actor_username,
        change_reason=reason,
        requires_retraining=requires_retraining,
    )
    if not updated:
        raise _fail("MATERIAL_NOT_FOUND", "找不到可管理的教材", 404)
    return {
        "ok": True,
        "material": updated,
        "version": int(updated.get("currentVersion") or 1),
        "requiredCompletionVersion": int(updated.get("requiredCompletionVersion") or 1),
        "requiresRetraining": requires_retraining,
    }


def restore_material_version(
    material_id: str,
    source_version: int,
    data: Mapping[str, Any],
    *,
    actor_username: str,
) -> dict:
    material_id = str(material_id or "").strip()
    entry = repository.get_material(material_id)
    if not entry:
        raise _fail("MATERIAL_NOT_FOUND", "找不到可管理的教材", 404)
    try:
        source_version = int(source_version)
    except (TypeError, ValueError):
        raise _fail("MATERIAL_VERSION_INVALID", "版本編號不正確")
    if source_version < 1 or source_version >= int(entry.get("currentVersion") or 1):
        raise _fail("MATERIAL_VERSION_RESTORE_INVALID", "只能回復目前版本以前的歷史版本")
    reason = str(data.get("changeReason") or "").strip()[:1000]
    if not reason:
        raise _fail("MATERIAL_VERSION_REASON_REQUIRED", "請輸入本次版本回復原因")
    requires_retraining = data.get("requiresRetraining", False)
    if type(requires_retraining) is not bool:
        raise _fail("MATERIAL_VERSION_RETRAINING_INVALID", "重新訓練設定格式不正確")
    actor_username = str(actor_username or "").strip()[:100]
    if not actor_username:
        raise _fail("MATERIAL_VERSION_ACTOR_REQUIRED", "無法確認版本發布者", 401)
    updated = repository.restore_material_version(
        material_id,
        source_version,
        published_by=actor_username,
        change_reason=reason,
        requires_retraining=requires_retraining,
    )
    if not updated:
        raise _fail("MATERIAL_VERSION_NOT_FOUND", "找不到指定的歷史版本", 404)
    return {
        "ok": True,
        "material": updated,
        "version": int(updated.get("currentVersion") or 1),
        "restoredFromVersion": source_version,
        "requiredCompletionVersion": int(updated.get("requiredCompletionVersion") or 1),
        "requiresRetraining": requires_retraining,
    }


def material_purge_readiness(material_id: str) -> dict:
    material = repository.get_material(material_id)
    graph = repository.material_artifact_reference_graph(material_id)
    return {
        **graph,
        "materialExists": bool(material),
        "title": str((material or {}).get("title") or ""),
    }


def purge_material_storage(material_id: str, *, paths, storage_runtime=None) -> dict:
    """Physically delete storage only after the caller has revalidated a blocker-free graph."""
    entry = repository.get_material(material_id)
    if not entry:
        raise _fail("MATERIAL_NOT_FOUND", "找不到要永久清除的教材。", 404)
    graph = repository.material_artifact_reference_graph(material_id)
    if not graph.get("purgeAllowed"):
        raise _fail("MATERIAL_PURGE_BLOCKED", "教材仍被版本或衍生內容引用，拒絕永久清除。", 409, referenceGraph=graph)

    backend = str(entry.get("storageBackend") or "local").lower()
    if backend not in canonical_storage.VALID_BACKENDS:
        backend = "local"

    def delete_local_material(payload):
        upload_dir = Path(paths.upload_dir) / payload["id"]
        slides_dir = Path(paths.uploaded_slides_dir) / payload["folder"]
        if upload_dir.exists():
            shutil.rmtree(upload_dir)
        if slides_dir.exists():
            shutil.rmtree(slides_dir)

    if backend == "gdrive":
        request = canonical_storage.DeleteRequest(backend, "material", entry)
    elif backend == "mega":
        meta = entry.get("storageMeta") or {}
        request = canonical_storage.DeleteRequest(
            backend, "object", meta.get("folderId") or meta.get("materialFolderId") or entry.get("storageKey", "")
        )
    elif backend in {"oci", "r2"}:
        request = canonical_storage.DeleteRequest(backend, "prefix", f"materials/{entry['id']}/")
    else:
        request = canonical_storage.DeleteRequest("local", "material", entry)

    adapters = (
        storage_runtime.delete_adapters(local_delete_material=delete_local_material)
        if storage_runtime is not None
        else WebStorageRuntime(paths).delete_adapters(local_delete_material=delete_local_material)
    )
    try:
        canonical_storage.delete_strict(request, adapters)
    except Exception as exc:
        cause = exc.cause if isinstance(exc, canonical_storage.StorageDeletionError) else exc
        raise _fail("MATERIAL_PURGE_STORAGE_FAILED", f"永久清除教材儲存失敗：{cause}", 502) from exc
    repository.delete_material_record(material_id)
    return {"ok": True, "purged": True, "backend": backend}


def delete_material(
    base_or_material_id,
    material_id: str | None = None,
    *,
    paths=None,
    storage_runtime=None,
) -> dict:
    """Strictly delete material storage before removing the canonical DB row."""
    base = None if material_id is None else base_or_material_id
    if material_id is None:
        material_id = str(base_or_material_id)
    else:
        material_id = str(material_id)
    entry = repository.get_material(material_id)
    if not entry:
        raise _fail("MATERIAL_NOT_FOUND", "內建教材不能從後台刪除，或找不到此教材", 404)

    backend = str(entry.get("storageBackend") or "local").lower()
    if backend not in canonical_storage.VALID_BACKENDS:
        backend = "local"

    version_refs = repository.material_version_storage_references(material_id)
    preserve_version_storage = bool(version_refs)

    if paths is None and base is not None:
        paths = SimpleNamespace(
            upload_dir=Path(base.UPLOAD_DIR),
            uploaded_slides_dir=Path(base.UPLOADED_SLIDES_DIR),
            preview_cache_dir=Path(base.PREVIEW_CACHE_DIR),
        )
    if paths is None:
        raise RuntimeError("StoragePaths is required for material deletion")

    def delete_local_material(payload):
        upload_dir = Path(paths.upload_dir) / payload["id"]
        slides_dir = Path(paths.uploaded_slides_dir) / payload["folder"]
        if upload_dir.exists():
            shutil.rmtree(upload_dir)
        if slides_dir.exists():
            shutil.rmtree(slides_dir)

    if backend == "gdrive":
        request = canonical_storage.DeleteRequest(backend, "material", entry)
    elif backend == "mega":
        meta = entry.get("storageMeta") or {}
        request = canonical_storage.DeleteRequest(
            backend,
            "object",
            meta.get("folderId") or meta.get("materialFolderId") or entry.get("storageKey", ""),
        )
    elif backend in {"oci", "r2"}:
        request = canonical_storage.DeleteRequest(backend, "prefix", f"materials/{entry['id']}/")
    else:
        request = canonical_storage.DeleteRequest("local", "material", entry)

    if storage_runtime is not None:
        adapters = storage_runtime.delete_adapters(local_delete_material=delete_local_material)
    elif base is not None and hasattr(base, "storage_delete_adapters"):
        adapters = base.storage_delete_adapters(local_delete_material=delete_local_material)
    else:
        adapters = WebStorageRuntime(paths).delete_adapters(local_delete_material=delete_local_material)
    try:
        # Version history is immutable and may be restored later.  If any
        # historical snapshot references provider storage, retain the provider
        # objects when removing the catalog row.  A dedicated retention purge
        # must prove references are gone before physical deletion.
        if not preserve_version_storage:
            canonical_storage.delete_strict(request, adapters)
    except Exception as exc:
        cause = exc.cause if isinstance(exc, canonical_storage.StorageDeletionError) else exc
        failures = {
            "gdrive": ("GDRIVE_DELETE_FAILED", "Google Drive 教材刪除失敗"),
            "mega": ("MEGA_DELETE_FAILED", "MEGA 教材刪除失敗"),
            "oci": ("OCI_DELETE_FAILED", "Oracle Object Storage 教材刪除失敗"),
            "r2": ("R2_DELETE_FAILED", "R2 教材刪除失敗"),
            "local": ("LOCAL_DELETE_FAILED", "本機教材刪除失敗"),
        }
        code, message = failures[backend]
        raise _fail(code, f"{message}：{cause}", 502) from exc

    try:
        cache_file = Path(paths.preview_cache_dir) / (re.sub(r"[^A-Za-z0-9_-]", "_", str(material_id)) + ".pdf")
        if cache_file.exists():
            cache_file.unlink()
    except OSError:
        pass

    repository.delete_material_record(material_id)
    return {"ok": True, "versionStorageRetained": preserve_version_storage, "retainedVersionCount": len(version_refs)}
