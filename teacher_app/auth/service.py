"""Authentication and session lifecycle, independent of HTTP responses."""

import datetime
import logging
import re
import json
import time

from flask import g, has_request_context

from werkzeug.security import check_password_hash

from teacher_app.auth import repository
from teacher_app.common.auth import (
    LEGACY_ROLE_ALIASES,
    normalize_role,
    normalize_roles,
)
from teacher_app.common.errors import ApiError


_LOG = logging.getLogger(__name__)
_REQUEST_USER_CACHE_ATTR = "_teacher_current_user_row"
_SLOW_AUTH_MS = 250.0


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
        user["professionalTitle"] = str(d.get("professional_title", "") or "")[:100]
        user["responsibilityTags"] = _profile_tags(d.get("responsibility_tags"))

    return user


def _profile_tags(value):
    """Fail closed to presentation-only empty tags for malformed legacy data."""
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = []
    if not isinstance(parsed, list):
        return []
    return [str(tag).strip()[:50] for tag in parsed if str(tag).strip()][:12]


def _load_current_user_row(base, session):
    username = normalize_username(session.get("username", ""))
    if not username:
        return None

    session_version = session.get("session_version", 0)
    cache_key = (username, str(session_version))
    if has_request_context():
        cached = getattr(g, _REQUEST_USER_CACHE_ATTR, None)
        if cached and cached.get("key") == cache_key:
            return cached.get("row")

    started = time.perf_counter()
    raw = repository.find_user(base, username)
    elapsed_ms = (time.perf_counter() - started) * 1000
    if elapsed_ms >= _SLOW_AUTH_MS:
        _LOG.warning("slow auth lookup: %.0fms", elapsed_ms)

    if not raw or not bool(raw.get("active", True)):
        session.clear()
        raw = None
    else:
        try:
            valid = int(raw.get("session_version", 1) or 1) == int(session_version or 0)
        except (TypeError, ValueError):
            valid = False
        if not valid:
            session.clear()
            raw = None

    if has_request_context():
        setattr(g, _REQUEST_USER_CACHE_ATTR, {"key": cache_key, "row": raw})
    return raw


def current_user(base, session, *, include_roles=False):
    """Resolve the authenticated user once per request, never across requests."""
    raw = _load_current_user_row(base, session)
    if not raw:
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
