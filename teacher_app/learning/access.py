"""Canonical learner-facing content visibility helpers.

Preferred area/group is the default learner scope. A formal active learning
assignment may grant access to the assigned course outside that default scope;
it does not grant access to unrelated content in the same foreign group.
"""
from __future__ import annotations

from typing import Any, Mapping

from teacher_app.common import scope
from teacher_app.common.auth import has_role


GLOBAL_LEARNING_ROLES = ("education_admin", "system_admin")
_SCOPE_KEYS = ("preferredArea", "preferred_area", "preferredGroup", "preferred_group")


def has_global_learning_access(user: Mapping[str, Any] | None) -> bool:
    return bool(user) and any(has_role(user, role) for role in GLOBAL_LEARNING_ROLES)


def has_explicit_learning_scope(user: Mapping[str, Any] | None) -> bool:
    return bool(user) and any(key in user for key in _SCOPE_KEYS)


def preferred_learning_scope(user: Mapping[str, Any] | None) -> tuple[str, str]:
    user = user or {}
    return (
        scope.normalize_area(user.get("preferredArea") or user.get("preferred_area") or scope.DEFAULT_TRAINING_AREA),
        scope.normalize_group(user.get("preferredGroup") or user.get("preferred_group") or scope.DEFAULT_GROUP),
    )


def item_learning_scope(item: Mapping[str, Any] | None) -> tuple[str, str]:
    item = item or {}
    return (
        scope.normalize_area(item.get("area") or item.get("trainingArea") or item.get("training_area") or scope.DEFAULT_TRAINING_AREA),
        scope.normalize_group(item.get("group") or item.get("groupKey") or item.get("group_key") or scope.DEFAULT_GROUP),
    )


def _assigned_rows(user: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not user:
        return []
    from teacher_app.learning import assignment_service
    return assignment_service.list_for_user(user)


def assigned_course_ids(user: Mapping[str, Any] | None) -> set[str]:
    return {str(item.get("courseId") or "").strip() for item in _assigned_rows(user) if str(item.get("courseId") or "").strip()}


def can_access_course(user: Mapping[str, Any] | None, course: Mapping[str, Any] | None) -> bool:
    if not user or not course:
        return False
    if has_global_learning_access(user) or not has_explicit_learning_scope(user):
        return True
    if item_learning_scope(course) == preferred_learning_scope(user):
        return True
    return str(course.get("id") or "").strip() in assigned_course_ids(user)


def can_access_learning_item(user: Mapping[str, Any] | None, item: Mapping[str, Any] | None) -> bool:
    if not user or not item:
        return False
    if has_global_learning_access(user) or not has_explicit_learning_scope(user):
        return True
    if item_learning_scope(item) == preferred_learning_scope(user):
        return True
    course_id = str(item.get("courseId") or item.get("course_id") or "").strip()
    return bool(course_id and course_id in assigned_course_ids(user))


def can_access_requested_scope(user: Mapping[str, Any] | None, area: object, group: object) -> bool:
    if not user:
        return False
    if has_global_learning_access(user) or not has_explicit_learning_scope(user):
        return True
    requested = (scope.normalize_area(area), scope.normalize_group(group))
    if requested == preferred_learning_scope(user):
        return True
    return any(item_learning_scope(item) == requested for item in _assigned_rows(user))


def assigned_courses_in_scope(user: Mapping[str, Any] | None, area: object, group: object) -> set[str]:
    requested = (scope.normalize_area(area), scope.normalize_group(group))
    return {
        str(item.get("courseId") or "").strip()
        for item in _assigned_rows(user)
        if item_learning_scope(item) == requested and str(item.get("courseId") or "").strip()
    }


__all__ = [
    "GLOBAL_LEARNING_ROLES", "assigned_course_ids", "assigned_courses_in_scope",
    "can_access_course", "can_access_learning_item", "can_access_requested_scope",
    "has_explicit_learning_scope", "has_global_learning_access", "item_learning_scope",
    "preferred_learning_scope",
]
