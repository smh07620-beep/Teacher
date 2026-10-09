"""Canonical learner-facing content visibility helpers.

A learner's persisted preferred training area/group remains the authoritative
personal learning scope. Content ownership and learner visibility are separate:
all materials/questions keep an owning group, while audience metadata may make
an item available to all staff or selected additional groups.

Production session users always carry preferred area/group. Isolated legacy
compatibility fixtures may omit both fields; those fixtures retain their prior
behavior so tests/adapters do not invent a false scope that production never
uses.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from teacher_app.common import scope
from teacher_app.common.auth import has_permission, has_role


GLOBAL_LEARNING_ROLES = ("education_admin", "system_admin")
_SCOPE_KEYS = (
    "preferredArea",
    "preferred_area",
    "preferredGroup",
    "preferred_group",
)
_AUDIENCE_SCOPES = {"group_only", "all_staff", "multi_group", "source_only"}


def has_global_learning_access(user: Mapping[str, Any] | None) -> bool:
    return bool(user) and any(has_role(user, role) for role in GLOBAL_LEARNING_ROLES)


def has_explicit_learning_scope(user: Mapping[str, Any] | None) -> bool:
    if not user:
        return False
    return any(key in user for key in _SCOPE_KEYS)


def preferred_learning_scope(user: Mapping[str, Any] | None) -> tuple[str, str]:
    user = user or {}
    area = scope.normalize_area(
        user.get("preferredArea")
        or user.get("preferred_area")
        or scope.DEFAULT_TRAINING_AREA
    )
    group = scope.normalize_group(
        user.get("preferredGroup")
        or user.get("preferred_group")
        or scope.DEFAULT_GROUP
    )
    return area, group


def item_learning_scope(item: Mapping[str, Any] | None) -> tuple[str, str]:
    item = item or {}
    area = scope.normalize_area(
        item.get("area")
        or item.get("trainingArea")
        or item.get("training_area")
        or scope.DEFAULT_TRAINING_AREA
    )
    group = scope.normalize_group(
        item.get("ownerGroup")
        or item.get("owner_group")
        or item.get("group")
        or item.get("groupKey")
        or item.get("group_key")
        or scope.DEFAULT_GROUP
    )
    return area, group


def _audience_scope(item: Mapping[str, Any] | None) -> str:
    item = item or {}
    candidate = str(
        item.get("audienceScope")
        or item.get("audience_scope")
        or "group_only"
    ).strip().lower()
    return candidate if candidate in _AUDIENCE_SCOPES else "group_only"


def _audience_groups(item: Mapping[str, Any] | None) -> set[str]:
    item = item or {}
    raw = item.get("audienceGroups")
    if raw is None:
        raw = item.get("audience_groups")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except (TypeError, ValueError):
            raw = [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(raw, (list, tuple, set)):
        return set()
    return {str(value).strip() for value in raw if str(value).strip() in scope.GROUPS}


def _username(user: Mapping[str, Any] | None) -> str:
    return str((user or {}).get("username") or "").strip().lower()


def personal_course_grants(user: Mapping[str, Any] | None) -> frozenset[str]:
    """Course ids this account was individually assigned, even from another group.

    An individual assignment is the explicit, audited grant that lets one person
    see one course (and its materials) outside their own group.  Only published,
    active courses in the person's own training area count.  Cached per request.
    """
    username = _username(user)
    if not username:
        return frozenset()
    cache = None
    try:
        from flask import g, has_request_context

        if has_request_context():
            cache = g.__dict__.setdefault("_personal_course_grants", {})
            if username in cache:
                return cache[username]
    except Exception:
        cache = None
    area, _group = preferred_learning_scope(user)
    granted: set[str] = set()
    try:
        from teacher_app.courses import repository as course_repository
        from teacher_app.learning import assignment_repository

        for course_id in assignment_repository.list_personal_course_ids(username=username, area=area):
            course = course_repository.get_course(course_id)
            if not course or not course.get("active", True):
                continue
            if str(course.get("lifecycleStatus") or "published") != "published":
                continue
            if scope.normalize_area(course.get("area")) != area:
                continue
            granted.add(course_id)
    except Exception:
        return frozenset()
    result = frozenset(granted)
    if cache is not None:
        cache[username] = result
    return result


def _item_course_id(item: Mapping[str, Any]) -> str:
    for key in ("courseId", "course_id"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    # A course record itself (no courseId key, carries a lifecycle status).
    if "lifecycleStatus" in item or "lifecycle_status" in item:
        return str(item.get("id") or "").strip()
    return ""


def can_access_learning_item(
    user: Mapping[str, Any] | None,
    item: Mapping[str, Any] | None,
) -> bool:
    if not user or not item:
        return False
    if _audience_scope(item) == "source_only":
        # 僅供老師製作使用：學員一律不可見（先於其他放行規則）。
        if has_global_learning_access(user):
            return True
        _area, owner = item_learning_scope(item)
        _user_area, user_group = preferred_learning_scope(user)
        authoring = any(has_permission(user, name) for name in ("material.manage", "question.manage", "course.manage"))
        return authoring and owner == user_group
    if has_global_learning_access(user):
        return True
    if not has_explicit_learning_scope(user):
        return True

    item_area, owner_group = item_learning_scope(item)
    user_area, user_group = preferred_learning_scope(user)
    if item_area != user_area:
        return False
    if owner_group == user_group:
        return True

    audience = _audience_scope(item)
    if audience == "all_staff":
        return True
    if audience == "multi_group" and user_group in _audience_groups(item):
        return True
    course_id = _item_course_id(item)
    return bool(course_id) and course_id in personal_course_grants(user)


def can_access_requested_scope(
    user: Mapping[str, Any] | None,
    area: object,
    group: object,
) -> bool:
    if not user:
        return False
    if has_global_learning_access(user):
        return True
    if not has_explicit_learning_scope(user):
        return True
    requested = (scope.normalize_area(area), scope.normalize_group(group))
    return requested == preferred_learning_scope(user)


__all__ = [
    "GLOBAL_LEARNING_ROLES",
    "can_access_learning_item",
    "can_access_requested_scope",
    "has_explicit_learning_scope",
    "has_global_learning_access",
    "item_learning_scope",
    "personal_course_grants",
    "preferred_learning_scope",
]
