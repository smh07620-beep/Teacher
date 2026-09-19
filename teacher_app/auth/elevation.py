"""Canonical short-lived elevation state and HTTP registration.

Elevation is an additional authorization step for high-impact administrative
operations.  Normal teaching work continues to use session RBAC and scope.
"""
from __future__ import annotations

import datetime as dt
import hmac
import os
from contextlib import contextmanager
from typing import Callable

from flask import g, jsonify, request, session

from teacher_app.auth.elevation_policy import SENSITIVE_RULES, required_permissions
from teacher_app.common import db as common_db
from teacher_app.common.auth import has_permission


TTL_SECONDS = 15 * 60
ELEVATION_ELIGIBLE_PERMISSIONS = (
    "user.manage",
    "system.manage",
    "storage.manage",
    "backup.manage",
    "education.cross_group.manage",
)


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


@contextmanager
def _read_scope(connection_factory: Callable | None = None):
    if connection_factory is None:
        with common_db.read_connection() as pair:
            yield pair
        return
    conn, kind = connection_factory()
    try:
        yield conn, kind
    finally:
        conn.close()


@contextmanager
def _write_scope(connection_factory: Callable | None = None):
    if connection_factory is None:
        with common_db.transaction() as pair:
            yield pair
        return
    conn, kind = connection_factory()
    try:
        yield conn, kind
    finally:
        conn.close()


def get_elevation(username: str, connection_factory: Callable | None = None) -> dict:
    with _read_scope(connection_factory) as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT elevated_at,expires_at,session_version "
            f"FROM admin_elevations WHERE username={ph}",
            (username,),
        ).fetchone()
    return dict(row) if row else {}


def store_elevation(
    username: str,
    *,
    elevated_at: str,
    expires_at: str,
    session_version: int,
    connection_factory: Callable | None = None,
) -> None:
    with _write_scope(connection_factory) as (conn, kind):
        values = (username, elevated_at, expires_at, session_version)
        if kind == "postgres":
            conn.execute(
                "INSERT INTO admin_elevations(username,elevated_at,expires_at,session_version) "
                "VALUES(%s,%s,%s,%s) ON CONFLICT(username) DO UPDATE SET "
                "elevated_at=EXCLUDED.elevated_at,expires_at=EXCLUDED.expires_at,"
                "session_version=EXCLUDED.session_version",
                values,
            )
        else:
            conn.execute(
                "INSERT INTO admin_elevations(username,elevated_at,expires_at,session_version) "
                "VALUES(?,?,?,?) ON CONFLICT(username) DO UPDATE SET "
                "elevated_at=excluded.elevated_at,expires_at=excluded.expires_at,"
                "session_version=excluded.session_version",
                values,
            )


def is_elevated(
    user,
    *,
    session_version: int,
    connection_factory: Callable | None = None,
) -> bool:
    if not user:
        return False
    state = get_elevation(str(user.get("username") or ""), connection_factory)
    if not state:
        return False
    return bool(
        str(state.get("expires_at") or "") > now().isoformat()
        and int(state.get("session_version") or 0) == int(session_version or 0)
    )


def register_admin_elevation(
    app,
    *,
    current_user: Callable[[], dict | None],
    connection_factory: Callable | None = None,
):
    if app.extensions.get("teacher_admin_elevation_68_registered"):
        return app

    def clear():
        session.pop("admin_elevation_marker", None)

    def elevated(user):
        return is_elevated(
            user,
            session_version=int(session.get("session_version", 0) or 0),
            connection_factory=connection_factory,
        )

    def require_elevated(*permissions):
        user = current_user()
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if permissions and not any(has_permission(user, permission) for permission in permissions):
            return jsonify({"error": "權限不足。"}), 403
        if not elevated(user):
            return jsonify({
                "error": "此操作會變更敏感系統資料，請重新驗證管理權限。",
                "elevationRequired": True,
                "elevationTtlSeconds": TTL_SECONDS,
            }), 428
        return None

    @app.post("/api/admin/elevation")
    def elevate():
        user = current_user()
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not any(has_permission(user, permission) for permission in ELEVATION_ELIGIBLE_PERMISSIONS):
            return jsonify({"error": "權限不足。"}), 403

        supplied = str((request.get_json(silent=True) or {}).get("password") or "")
        key = os.environ.get("ADMIN_KEY", "").strip()
        if not key or not supplied or not hmac.compare_digest(supplied, key):
            return jsonify({"error": "驗證失敗。"}), 401

        stamp = now()
        expires = stamp + dt.timedelta(seconds=TTL_SECONDS)
        store_elevation(
            str(user["username"]),
            elevated_at=stamp.isoformat(),
            expires_at=expires.isoformat(),
            session_version=int(session.get("session_version", 0) or 0),
            connection_factory=connection_factory,
        )
        session["admin_elevation_marker"] = expires.isoformat()
        return jsonify({"ok": True, "expiresAt": expires.isoformat(), "ttlSeconds": TTL_SECONDS})

    @app.get("/api/admin/elevation")
    def elevation_status():
        user = current_user()
        if not user:
            return jsonify({"elevated": False})
        state = get_elevation(str(user["username"]), connection_factory)
        ok = bool(
            state
            and str(state.get("expires_at") or "") > now().isoformat()
            and int(state.get("session_version") or 0)
            == int(session.get("session_version", 0) or 0)
        )
        return jsonify({
            "elevated": ok,
            "expiresAt": str(state.get("expires_at") or "") if ok else "",
            "ttlSeconds": TTL_SECONDS,
        })

    @app.after_request
    def elevation_logout_clear(response):
        if request.path == "/api/auth/logout":
            clear()
        return response

    app.extensions["teacher_admin_elevation_check"] = elevated
    app.extensions["teacher_require_elevated_permission"] = require_elevated
    app.extensions["teacher_admin_elevation_68_registered"] = True
    return app


def register_admin_elevation_compat(base):
    """Bind canonical elevation behavior to the legacy application host seam."""
    app = register_admin_elevation(
        base.app,
        current_user=base._current_user,
        connection_factory=None,
    )
    base.is_admin_elevated = app.extensions["teacher_admin_elevation_check"]
    base.require_elevated_permission = app.extensions["teacher_require_elevated_permission"]
    return app


def register_sensitive_elevation(owner):
    """Enforce short-lived elevation on the canonical sensitive path policy."""
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_sensitive_elevation_69_registered"):
        return app

    @app.before_request
    def sensitive_elevation_boundary():
        permissions = required_permissions(request.method, request.path)
        if not permissions:
            return None

        user = getattr(g, "teacher_user", None)
        if user is None:
            resolver = getattr(owner, "_current_user", None)
            if callable(resolver):
                user = resolver()
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not any(has_permission(user, permission) for permission in permissions):
            return jsonify({"error": "權限不足。"}), 403

        guard = app.extensions.get("teacher_require_elevated_permission")
        if guard is None:
            guard = getattr(owner, "require_elevated_permission", None)
        if guard is None:
            return jsonify({
                "error": "敏感操作驗證服務尚未啟用。",
                "elevationRequired": True,
            }), 503
        return guard(*permissions)

    app.extensions["teacher_sensitive_elevation_69_registered"] = True
    return app


__all__ = [
    "ELEVATION_ELIGIBLE_PERMISSIONS",
    "TTL_SECONDS",
    "SENSITIVE_RULES",
    "get_elevation",
    "is_elevated",
    "now",
    "register_admin_elevation",
    "register_admin_elevation_compat",
    "register_sensitive_elevation",
    "required_permissions",
    "store_elevation",
]
