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
from teacher_app.common.auth import has_role


GLOBAL_LEARNING_ROLES = ("education_admin", "system_admin")
_SCOPE_KEYS = (
    "preferredArea",
    "preferred_area",
    "preferredGroup",
    "preferred_group",
)
_AUDIENCE_SCOPES = {"group_only", "all_staff", "multi_group"}


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


def can_access_learning_item(
    user: Mapping[str, Any] | None,
    item: Mapping[str, Any] | None,
) -> bool:
    if not user or not item:
        return False
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
    if audience == "multi_group":
        return user_group in _audience_groups(item)
    return False


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
    "preferred_learning_scope",
]
