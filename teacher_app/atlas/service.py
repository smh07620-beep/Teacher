"""Canonical Atlas business rules for scope, filtering and CRUD."""
from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from typing import Any, Mapping, Optional

from teacher_app.atlas import repository
from teacher_app.common.auth import has_permission, has_role, is_system_admin
from teacher_app.common.errors import ApiError


ATLAS_CATEGORIES = {"microscope", "blood_cell", "urine_sediment", "colony"}
MAX_QUERY = 200


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalise(value: Any) -> str:
    return re.sub(r"[\s_\-]+", " ", str(value or "").casefold()).strip()


def tags(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else str(value or "").split(",")
    return [str(item).strip()[:80] for item in raw if str(item).strip()][:20]


def group_allowed(user: Mapping[str, Any], group: str) -> bool:
    if is_system_admin(user) or has_role(user, "education_admin"):
        return True
    preferred = str(
        user.get("preferredGroup") or user.get("preferred_group") or ""
    )
    return preferred == str(group)


def readable_groups(user: Mapping[str, Any]) -> Optional[set[str]]:
    if is_system_admin(user) or has_role(user, "education_admin"):
        return None
    group = str(
        user.get("preferredGroup") or user.get("preferred_group") or ""
    ).strip()
    return {group} if group else set()


def can_read(user: Mapping[str, Any]) -> bool:
    return has_permission(user, "material.read") or has_role(user, "auditor")


def can_manage(user: Mapping[str, Any], group: str) -> bool:
    return has_permission(user, "material.manage") and group_allowed(user, group)


def material_visible(user: Mapping[str, Any], material: Optional[Mapping[str, Any]]) -> bool:
    if not material or not material.get("active", True) or not can_read(user):
        return False
    groups = readable_groups(user)
    material_group = str(material.get("group") or material.get("groupKey") or "")
    return groups is None or material_group in groups


def image_visible(user: Mapping[str, Any], image_url: str) -> bool:
    record = repository.get_image_access(image_url)
    if not record or not can_read(user):
        return False
    group = str(record.get("group_key") or "")
    groups = readable_groups(user)
    if groups is not None and group not in groups:
        return False
    if not bool(record.get("published")) and not can_manage(user, group):
        return False
    return True


def list_items(
    user: Mapping[str, Any],
    *,
    category: str = "",
    group_filter: str = "",
    tag_filter: str = "",
    status_filter: str = "",
    query: str = "",
) -> list[dict]:
    if not can_read(user):
        raise ApiError("ATLAS_FORBIDDEN", "權限不足。", status=403)
    status_filter = str(status_filter or "").strip().lower()
    if status_filter not in {"", "published", "draft"}:
        raise ApiError("INVALID_ATLAS_STATUS", "發布狀態篩選不正確。", status=400)
    tag_filter = normalise(tag_filter)[:80]
    query = normalise(query)[:MAX_QUERY]
    groups = readable_groups(user)
    result: list[dict] = []
    for item in repository.list_items():
        group = str(item.get("group") or "")
        if groups is not None and group not in groups:
            continue
        manageable = can_manage(user, group)
        if not manageable and not item.get("published"):
            continue
        if group_filter and group != group_filter:
            continue
        if tag_filter and tag_filter not in {normalise(tag) for tag in item.get("tags", [])}:
            continue
        if status_filter == "published" and not item.get("published"):
            continue
        if status_filter == "draft" and (not manageable or item.get("published")):
            continue
        if category and item.get("category") != category:
            continue
        hay = normalise(" ".join([
            str(item.get("title") or ""),
            str(item.get("description") or ""),
            " ".join(item.get("tags") or []),
            str(item.get("differentialPoints") or ""),
        ]))
        if query and query not in hay:
            continue
        result.append(item)
    return result


def get_item(user: Mapping[str, Any], item_id: str) -> dict:
    item = repository.get_item(item_id)
    if not item or not can_read(user):
        raise ApiError("ATLAS_NOT_FOUND", "找不到圖譜。", status=404)
    groups = readable_groups(user)
    if groups is not None and str(item.get("group") or "") not in groups:
        raise ApiError("ATLAS_NOT_FOUND", "找不到圖譜。", status=404)
    if not item.get("published") and not can_manage(user, str(item.get("group") or "")):
        raise ApiError("ATLAS_NOT_FOUND", "找不到圖譜。", status=404)
    return item


def _username(user: Mapping[str, Any]) -> str:
    return str(user.get("username") or "")


def create_item(user: Mapping[str, Any], body: Mapping[str, Any]) -> str:
    group = str(body.get("group") or "").strip()
    if not can_manage(user, group):
        raise ApiError("ATLAS_FORBIDDEN", "無權管理此組圖譜。", status=403)
    category = str(body.get("category") or "").strip()
    if category not in ATLAS_CATEGORIES:
        raise ApiError("INVALID_ATLAS_CATEGORY", "圖譜類別不正確。", status=400)
    title = str(body.get("title") or "").strip()[:255]
    if not title:
        raise ApiError("ATLAS_TITLE_REQUIRED", "請填寫圖譜名稱。", status=400)
    source = str(body.get("source") or "manual").strip()
    if source not in {"manual", "docx", "material"}:
        raise ApiError("INVALID_ATLAS_SOURCE", "匯入來源不正確。", status=400)
    timestamp = now()
    username = _username(user)
    item_id = uuid.uuid4().hex
    values = {
        "id": item_id,
        "category": category,
        "group_key": group,
        "title": title,
        "image_url": str(body.get("imageUrl") or "").strip()[:2000],
        "description": str(body.get("description") or "")[:6000],
        "tags": json.dumps(tags(body.get("tags")), ensure_ascii=False),
        "differential_points": str(body.get("differentialPoints") or "")[:6000],
        "teaching_notes": str(body.get("teachingNotes") or "")[:6000],
        "difficulty": str(body.get("difficulty") or "general")[:40],
        "published": bool(body.get("published", False)),
        "source": source,
        "source_material_id": str(body.get("sourceMaterialId") or "")[:100],
        "source_docx": str(body.get("sourceDocx") or "")[:255],
        "sort_order": int(body.get("sortOrder") or 0),
        "annotation_json": json.dumps(
            body.get("annotationJson") if isinstance(body.get("annotationJson"), dict) else {},
            ensure_ascii=False,
        ),
        "created_at": timestamp,
        "updated_at": timestamp,
        "created_by": username,
        "updated_by": username,
    }
    repository.insert_item(values)
    return item_id


def update_item(user: Mapping[str, Any], item_id: str, body: Mapping[str, Any]) -> None:
    item = repository.get_item(item_id)
    if not item:
        raise ApiError("ATLAS_NOT_FOUND", "找不到圖譜。", status=404)
    current_group = str(item.get("group") or "")
    if not can_manage(user, current_group):
        raise ApiError("ATLAS_FORBIDDEN", "無權管理此圖譜。", status=403)
    if "group" in body:
        next_group = str(body.get("group") or "").strip()
        if not next_group or not can_manage(user, next_group):
            raise ApiError("ATLAS_MOVE_FORBIDDEN", "無權移動至此組別。", status=403)

    allowed = {
        "title": "title",
        "imageUrl": "image_url",
        "description": "description",
        "differentialPoints": "differential_points",
        "teachingNotes": "teaching_notes",
        "difficulty": "difficulty",
        "sourceDocx": "source_docx",
        "sortOrder": "sort_order",
        "published": "published",
        "category": "category",
        "group": "group_key",
    }
    changes: dict[str, Any] = {}
    for key, column in allowed.items():
        if key not in body:
            continue
        value = body[key]
        if key == "category" and value not in ATLAS_CATEGORIES:
            raise ApiError("INVALID_ATLAS_CATEGORY", "圖譜類別不正確。", status=400)
        if key == "published":
            value = bool(value)
        changes[column] = value
    if "tags" in body:
        changes["tags"] = json.dumps(tags(body["tags"]), ensure_ascii=False)
    if "annotationJson" in body:
        changes["annotation_json"] = json.dumps(
            body["annotationJson"] if isinstance(body["annotationJson"], dict) else {},
            ensure_ascii=False,
        )
    repository.update_item(
        item_id,
        changes,
        updated_at=now(),
        updated_by=_username(user),
    )


def delete_item(user: Mapping[str, Any], item_id: str, *, confirmed: bool) -> None:
    if not confirmed:
        raise ApiError(
            "ATLAS_DELETE_CONFIRMATION_REQUIRED",
            "請確認刪除圖譜。",
            status=400,
            extra={"confirmationRequired": True},
        )
    item = repository.get_item(item_id)
    if not item:
        raise ApiError("ATLAS_NOT_FOUND", "找不到圖譜。", status=404)
    if not can_manage(user, str(item.get("group") or "")):
        raise ApiError("ATLAS_FORBIDDEN", "無權管理此圖譜。", status=403)
    repository.delete_item(item_id)
