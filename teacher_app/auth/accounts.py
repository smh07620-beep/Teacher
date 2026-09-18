"""Canonical account-administration rules for legacy `/api/users` routes."""
from __future__ import annotations

import datetime
import json

from werkzeug.security import generate_password_hash

from teacher_app.auth import repository, service as auth_service
from teacher_app.common import scope
from teacher_app.common.auth import (
    CANONICAL_ROLES,
    LEGACY_ROLE_ALIASES,
    normalize_role,
    normalize_roles,
)


class AccountNotFound(LookupError):
    pass


def _json_roles(roles) -> str:
    return json.dumps(list(roles), ensure_ascii=False, separators=(",", ":"))


def profile_title(value) -> str:
    return str(value or "").strip()[:100]


def profile_tags(value) -> str | None:
    """Validate presentation-only responsibility tags, never RBAC inputs."""
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("額外職責標籤必須為陣列。")
    tags = []
    for item in value:
        tag = str(item or "").strip()[:50]
        if tag and tag not in tags:
            tags.append(tag)
    if len(tags) > 12:
        raise ValueError("額外職責標籤最多 12 個。")
    return json.dumps(tags, ensure_ascii=False, separators=(",", ":"))


def validate_raw_roles(value) -> None:
    if value is None:
        return
    if isinstance(value, str):
        raw = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raise ValueError("roles 必須為角色陣列。")
    for item in raw:
        code = str(item or "").strip().lower()
        if code not in CANONICAL_ROLES and code not in LEGACY_ROLE_ALIASES:
            raise ValueError(f"角色格式不正確：{code}")


def roles_for_create(data):
    requested_role = str(data.get("role", "student")).strip().lower()
    if requested_role not in CANONICAL_ROLES and requested_role not in LEGACY_ROLE_ALIASES:
        raise ValueError("角色格式不正確。")
    validate_raw_roles(data.get("roles"))
    primary = normalize_role(requested_role)
    return primary, normalize_roles(data.get("roles"), primary=primary)


def roles_for_update(data, current):
    current_primary = normalize_role(current.get("role", "student"))
    current_roles = normalize_roles(current.get("roles_json"), primary=current_primary)
    if "role" not in data and "roles" not in data:
        return current_primary, current_roles, False

    if "role" in data:
        requested = str(data.get("role", "")).strip().lower()
        if requested not in CANONICAL_ROLES and requested not in LEGACY_ROLE_ALIASES:
            raise ValueError("角色格式不正確。")
        primary = normalize_role(requested)
    else:
        primary = current_primary

    if "roles" in data:
        validate_raw_roles(data.get("roles"))
        roles = normalize_roles(data.get("roles"), primary=primary)
    elif "role" in data:
        roles = [primary]
    else:
        roles = current_roles
    if primary not in roles:
        roles.insert(0, primary)
    return primary, roles, primary != current_primary or roles != current_roles


def list_accounts(base=None) -> list[dict]:
    del base
    return [
        auth_service.public_user(row, include_roles=True)
        for row in repository.list_users()
    ]


def create_account(base_or_data, data: dict | None = None) -> dict:
    data = base_or_data if data is None else data
    username = auth_service.normalize_username(data.get("username"))
    password = str(data.get("password", ""))
    name = str(data.get("name", "")).strip()[:100]
    emp_id = str(data.get("empId", "")).strip()[:100]
    if len(username) < 3 or len(password) < 4 or not name or not emp_id:
        raise ValueError("帳號至少 3 碼、密碼至少 4 碼，姓名與工號皆為必填。")

    role, roles = roles_for_create(data)
    professional_title = profile_title(data.get("professionalTitle"))
    responsibility_tags = profile_tags(data.get("responsibilityTags", []))
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    values = {
        "username": username,
        "password_hash": generate_password_hash(password),
        "display_name": name,
        "emp_id": emp_id,
        "role": role,
        "roles_json": _json_roles(roles),
        "preferred_area": scope.normalize_area(data.get("preferredArea", scope.DEFAULT_TRAINING_AREA)),
        "preferred_group": scope.normalize_group(data.get("preferredGroup", scope.DEFAULT_GROUP)),
        "active": True,
        "session_version": 1,
        "created_at": now,
        "updated_at": now,
        "last_login_at": "",
    }
    if repository.profile_columns_available():
        values["professional_title"] = professional_title
        values["responsibility_tags"] = responsibility_tags
    created = repository.create_user(values)
    return auth_service.public_user(created, include_roles=True)


def update_account(base_or_username, username_or_data, data: dict | None = None) -> dict:
    if data is None:
        username = base_or_username
        data = username_or_data
    else:
        username = username_or_data
    username = auth_service.normalize_username(username)
    current = repository.find_user(username)
    if not current:
        raise AccountNotFound("找不到帳號。")

    updates: dict[str, object] = {}
    mapping = {
        "name": "display_name",
        "empId": "emp_id",
        "preferredArea": "preferred_area",
        "preferredGroup": "preferred_group",
        "professionalTitle": "professional_title",
    }
    for key, column in mapping.items():
        if key not in data:
            continue
        value = str(data.get(key, "")).strip()[:100]
        if key == "preferredArea":
            value = scope.normalize_area(value)
        elif key == "preferredGroup":
            value = scope.normalize_group(value)
        if key in {"name", "empId"} and not value:
            raise ValueError("姓名與工號不可空白。")
        updates[column] = value

    if "responsibilityTags" in data:
        updates["responsibility_tags"] = profile_tags(data.get("responsibilityTags"))

    role, roles, roles_changed = roles_for_update(data, current)
    invalidate_session = roles_changed
    if roles_changed:
        updates["role"] = role
        updates["roles_json"] = _json_roles(roles)

    if "active" in data:
        active = data.get("active")
        if type(active) is not bool:
            raise ValueError("帳號狀態格式不正確。")
        updates["active"] = active
        if not active:
            invalidate_session = True

    password = str(data.get("password", ""))
    if password:
        if len(password) < 4:
            raise ValueError("新密碼至少 4 碼。")
        updates["password_hash"] = generate_password_hash(password)
        invalidate_session = True

    if not updates:
        raise ValueError("沒有可更新的欄位。")
    updates["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    updated = repository.update_user(
        username,
        updates,
        invalidate_session=invalidate_session,
    )
    if not updated:
        raise AccountNotFound("找不到帳號。")
    return auth_service.public_user(updated, include_roles=True)


__all__ = [
    "AccountNotFound",
    "create_account",
    "list_accounts",
    "profile_tags",
    "profile_title",
    "roles_for_create",
    "roles_for_update",
    "update_account",
    "validate_raw_roles",
]
