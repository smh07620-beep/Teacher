"""Canonical learner-facing content visibility helpers.

Until general course assignments exist, a learner's persisted preferred training
area/group is the authoritative personal learning scope. Organization/system
administrators may inspect all learning content, but ordinary learner/teacher
surfaces must not silently mix other groups into progress or completion data.

Production session users always carry preferred area/group. Isolated legacy
compatibility fixtures may omit both fields; those fixtures retain their prior
behavior so tests/adapters do not invent a false scope that production never
uses.
"""
from __future__ import annotations

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
        item.get("group")
        or item.get("groupKey")
        or item.get("group_key")
        or scope.DEFAULT_GROUP
    )
    return area, group


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
    return item_learning_scope(item) == preferred_learning_scope(user)


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
