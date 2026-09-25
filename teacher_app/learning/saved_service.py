"""Policy for cross-device learner save-for-later markers."""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping

from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.learning import access as learning_access
from teacher_app.learning import saved_repository
from teacher_app.materials import repository as material_repository

VALID_ITEM_TYPES = {"course", "material"}


def _fail(code: str, message: str, status: int) -> ApiError:
    return ApiError(code, message, status=status)


def _username(user: Mapping[str, Any] | None) -> str:
    username = str((user or {}).get("username") or "").strip()
    if not username:
        raise _fail("AUTH_REQUIRED", "請先登入。", 401)
    return username


def _normalize_type(item_type: Any) -> str:
    value = str(item_type or "").strip().lower()
    if value not in VALID_ITEM_TYPES:
        raise _fail("INVALID_SAVED_ITEM_TYPE", "收藏類型只支援 course 或 material。", 400)
    return value


def _resolve_visible(user: Mapping[str, Any] | None, item_type: str, item_id: str) -> dict | None:
    item = course_repository.get_course(item_id) if item_type == "course" else material_repository.get_material(item_id)
    if not item or not item.get("active", True) or not learning_access.can_access_learning_item(user, item):
        return None
    return item


def _project(item_type: str, item: Mapping[str, Any], saved_at: str) -> dict:
    return {
        "itemType": item_type,
        "itemId": str(item.get("id") or ""),
        "title": str(item.get("title") or item.get("filename") or ""),
        "area": str(item.get("area") or ""),
        "group": str(item.get("group") or ""),
        "courseId": str(item.get("courseId") or "") if item_type == "material" else str(item.get("id") or ""),
        "materialType": str(item.get("materialType") or "") if item_type == "material" else "",
        "savedAt": saved_at,
    }


def list_saved_items(user: Mapping[str, Any] | None) -> list[dict]:
    username = _username(user)
    output: list[dict] = []
    for marker in saved_repository.list_saved(username):
        try:
            item_type = _normalize_type(marker.get("itemType"))
        except ApiError:
            continue
        item_id = str(marker.get("itemId") or "").strip()
        item = _resolve_visible(user, item_type, item_id)
        if not item:
            continue
        output.append(_project(item_type, item, str(marker.get("savedAt") or "")))
    return output


def set_saved_item(user: Mapping[str, Any] | None, item_type: Any, item_id: Any, *, saved: bool) -> dict:
    username = _username(user)
    normalized_type = _normalize_type(item_type)
    normalized_id = str(item_id or "").strip()
    if not normalized_id or len(normalized_id) > 200:
        raise _fail("INVALID_SAVED_ITEM_ID", "收藏項目識別碼格式錯誤。", 400)
    if saved:
        item = _resolve_visible(user, normalized_type, normalized_id)
        if not item:
            raise _fail("LEARNING_ITEM_NOT_FOUND", "找不到可存取的學習項目。", 404)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    saved_repository.set_saved(username, normalized_type, normalized_id, saved=saved, now=now)
    return {"ok": True, "itemType": normalized_type, "itemId": normalized_id, "saved": saved, "savedAt": now if saved else ""}


__all__ = ["list_saved_items", "set_saved_item"]
