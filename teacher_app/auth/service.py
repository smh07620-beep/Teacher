"""Authentication and session lifecycle, independent of HTTP responses."""

import datetime
import re

from werkzeug.security import check_password_hash

from teacher_app.auth import repository
from teacher_app.common.auth import (
    LEGACY_ROLE_ALIASES,
    normalize_role,
    normalize_roles,
)
from teacher_app.common.errors import ApiError


def normalize_username(value):
    return re.sub(r"[^a-z0-9._-]", "", str(value or "").strip().lower())[:64]


def public_user(base, row, *, include_roles=False):
    d = dict(row)

    primary_role = normalize_role(
        d.get("role", "student")
    )

    user = {
        "username": str(d.get("username", "")),
        "name": str(d.get("display_name", "")),
        "empId": str(d.get("emp_id", "")),
        "role": primary_role,
        "legacyRole": str(d.get("role", "")) if str(d.get("role", "")) in LEGACY_ROLE_ALIASES else "",
        "preferredArea": base.normalize_area(d.get("preferred_area", base.DEFAULT_TRAINING_AREA)),
        "preferredGroup": base.normalize_group(d.get("preferred_group", base.DEFAULT_GROUP)),
        "active": bool(d.get("active", True)),
        "createdAt": str(d.get("created_at", "")),
        "updatedAt": str(d.get("updated_at", "")),
        "lastLoginAt": str(d.get("last_login_at", "")),
    }

    if include_roles:
        user["roles"] = normalize_roles(
            d.get("roles_json"),
            primary=primary_role,
        )

    return user


def current_user(base, session, *, include_roles=False):
    username = normalize_username(session.get("username", ""))
    if not username:
        return None
    raw = repository.find_user(base, username)
    if not raw or not bool(raw.get("active", True)):
        session.clear()
        return None
    try:
        valid = int(raw.get("session_version", 1) or 1) == int(session.get("session_version", 0) or 0)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        session.clear()
        return None
    return public_user(
        base,
        raw,
        include_roles=include_roles,
    )


def login(base, data, session):
    username = normalize_username(data.get("username"))
    password = str(data.get("password", ""))
    raw = repository.find_user(base, username)
    if not raw or not bool(raw.get("active", True)) or not check_password_hash(str(raw.get("password_hash", "")), password):
        raise ApiError("INVALID_CREDENTIALS", "帳號或密碼不正確，請洽管理者。", status=401)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    repository.record_login(base, username, now)
    raw["last_login_at"] = now
    user = public_user(base, raw)
    session.clear()
    session.permanent = True
    session["username"] = username
    session["session_version"] = int(raw.get("session_version", 1) or 1)
    return {"ok": True, "user": user}


def logout(session):
    session.clear()
    return {"ok": True}
