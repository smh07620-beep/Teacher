"""Canonical RBAC helpers for Teacher 6.5.

Both legacy adapters and modular services import this single policy.
Authentication and session validation live in teacher_app.auth.service.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from teacher_app.common.errors import ApiError

LEGACY_ROLE_ALIASES = {
    "learner": "student",
    "teacher": "clinical_teacher",
    "manager": "education_admin",
}

CANONICAL_ROLES = {
    "student",
    "clinical_teacher",
    "group_leader",
    "education_admin",
    "system_admin",
    "auditor",
}

ROLE_PERMISSIONS = {
    "student": {"course.view", "exam.take", "student.view_self"},
    "clinical_teacher": {
        "course.view",
        "evaluation.submit",
        "evaluation.review",
        "evaluation.sign",
        "student.view_assigned",
    },
    "group_leader": {
        "course.view",
        "course.edit",
        "exam.manage",
        "evaluation.review",
        "evaluation.countersign",
        "student.view_group",
    },
    "education_admin": {
        "course.view",
        "course.edit",
        "exam.manage",
        "evaluation.finalize",
        "student.view_all",
        "user.manage",
    },
    "system_admin": {"user.manage", "role.manage", "audit.view", "system.manage"},
    "auditor": {"audit.view"},
}

ROLE_LABELS = {
    "student": "學員",
    "clinical_teacher": "臨床教師",
    "group_leader": "組長",
    "education_admin": "教學管理者",
    "system_admin": "系統管理者",
    "auditor": "稽核／唯讀",
}


def normalize_role(value: Any) -> str:
    role = str(value or "student").strip().lower()
    role = LEGACY_ROLE_ALIASES.get(role, role)
    return role if role in CANONICAL_ROLES else "student"


def normalize_roles(value: Any, primary: Any = None) -> list[str]:
    """Normalize multi-role input while preserving the legacy primary role."""
    raw_items = []

    if isinstance(value, str):
        stripped = value.strip()

        if stripped:
            try:
                parsed = json.loads(stripped)

                if isinstance(parsed, list):
                    raw_items = parsed
                else:
                    raw_items = [
                        item.strip()
                        for item in stripped.split(",")
                        if item.strip()
                    ]
            except Exception:
                raw_items = [
                    item.strip()
                    for item in stripped.split(",")
                    if item.strip()
                ]

    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)

    elif value:
        raw_items = [value]

    normalized = []

    primary_role = normalize_role(primary) if primary is not None else ""

    if primary_role:
        normalized.append(primary_role)

    for item in raw_items:
        role = normalize_role(item)

        if role not in normalized:
            normalized.append(role)

    if not normalized:
        normalized = [
            normalize_role(
                primary if primary is not None else "student"
            )
        ]

    return normalized


def user_roles(user: Optional[Mapping[str, Any]]) -> list[str]:
    if not user:
        return []

    primary = user.get("role", "student")

    if "roles" in user:
        source = user.get("roles")
    else:
        source = user.get("roles_json")

    return normalize_roles(
        source,
        primary=primary,
    )


def has_role(user: Optional[Mapping[str, Any]], role: str) -> bool:
    return normalize_role(role) in user_roles(user)


def has_permission(user: Optional[Mapping[str, Any]], permission: str) -> bool:
    if not user:
        return False

    return any(
        permission in ROLE_PERMISSIONS.get(role, set())
        for role in user_roles(user)
    )


def require_role(user: Optional[Mapping[str, Any]], *allowed_roles: str) -> Mapping[str, Any]:
    if not user:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入後再執行此操作。",
            status=401,
        )

    allowed = {
        normalize_role(role)
        for role in allowed_roles
    }

    if not any(
        role in allowed
        for role in user_roles(user)
    ):
        expected = "、".join(
            ROLE_LABELS.get(role, role)
            for role in allowed
        )

        raise ApiError(
            "FORBIDDEN",
            f"權限不足：此操作限{expected}使用。",
            status=403,
        )

    return user


def require_permission(user: Optional[Mapping[str, Any]], permission: str) -> Mapping[str, Any]:
    if not user:
        raise ApiError("LOGIN_REQUIRED", "請先登入後再執行此操作。", status=401)
    if not has_permission(user, permission):
        raise ApiError("FORBIDDEN", "權限不足。", status=403)
    return user


def can_teacher_sign(user: Optional[Mapping[str, Any]]) -> bool:
    """Clinical signature is never granted to system_admin or education_admin."""
    return has_permission(user, "evaluation.sign")
