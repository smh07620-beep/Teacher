"""Server-side short lived elevation for sensitive administrative actions.

Normal teaching/content workflows are authorized by the authenticated session
and canonical RBAC.  Elevation is deliberately reserved for account, storage,
backup, and destructive system operations.
"""
from __future__ import annotations

import datetime as dt
import hmac
import os

from flask import jsonify, request, session

from teacher_app.common.auth import has_permission


TTL_SECONDS = 15 * 60
ELEVATION_ELIGIBLE_PERMISSIONS = (
    "user.manage",
    "system.manage",
    "storage.manage",
    "backup.manage",
    # Education administrators historically own logical backup/restore even
    # though backup.manage itself is system-admin-only in the canonical matrix.
    "education.cross_group.manage",
)


def now():
    return dt.datetime.now(dt.timezone.utc)


def register_admin_elevation(base):
    app = base.app
    if app.extensions.get("teacher_admin_elevation_68_registered"):
        return app

    def clear():
        session.pop("admin_elevation_marker", None)

    def elevated(user):
        if not user:
            return False
        conn, kind = base._db_conn()
        ph = "%s" if kind == "postgres" else "?"
        try:
            row = conn.execute(
                f"SELECT expires_at,session_version FROM admin_elevations WHERE username={ph}",
                (user["username"],),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return False
        data = dict(row)
        return bool(
            str(data.get("expires_at") or "") > now().isoformat()
            and int(data.get("session_version") or 0)
            == int(session.get("session_version", 0) or 0)
        )

    def require_elevated(*permissions):
        user = base._current_user()
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
        user = base._current_user()
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
        username = user["username"]
        conn, kind = base._db_conn()
        ph = "%s" if kind == "postgres" else "?"
        try:
            vals = (
                username,
                stamp.isoformat(),
                expires.isoformat(),
                int(session.get("session_version", 0) or 0),
            )
            if kind == "postgres":
                conn.execute(
                    "INSERT INTO admin_elevations(username,elevated_at,expires_at,session_version) "
                    "VALUES(%s,%s,%s,%s) ON CONFLICT(username) DO UPDATE SET "
                    "elevated_at=EXCLUDED.elevated_at,expires_at=EXCLUDED.expires_at,"
                    "session_version=EXCLUDED.session_version",
                    vals,
                )
            else:
                conn.execute(
                    "INSERT INTO admin_elevations(username,elevated_at,expires_at,session_version) "
                    "VALUES(?,?,?,?) ON CONFLICT(username) DO UPDATE SET "
                    "elevated_at=excluded.elevated_at,expires_at=excluded.expires_at,"
                    "session_version=excluded.session_version",
                    vals,
                )
        finally:
            conn.close()
        session["admin_elevation_marker"] = expires.isoformat()
        return jsonify({"ok": True, "expiresAt": expires.isoformat(), "ttlSeconds": TTL_SECONDS})

    @app.get("/api/admin/elevation")
    def elevation_status():
        user = base._current_user()
        if not user:
            return jsonify({"elevated": False})
        ok = elevated(user)
        conn, kind = base._db_conn()
        ph = "%s" if kind == "postgres" else "?"
        try:
            row = conn.execute(
                f"SELECT expires_at FROM admin_elevations WHERE username={ph}",
                (user["username"],),
            ).fetchone()
        finally:
            conn.close()
        return jsonify({
            "elevated": ok,
            "expiresAt": dict(row).get("expires_at", "") if ok and row else "",
            "ttlSeconds": TTL_SECONDS,
        })

    @app.after_request
    def elevation_logout_clear(response):
        if request.path == "/api/auth/logout":
            clear()
        return response

    # Export one canonical guard so later adapters do not duplicate elevation
    # storage/session logic.
    base.is_admin_elevated = elevated
    base.require_elevated_permission = require_elevated
    app.extensions["teacher_admin_elevation_check"] = elevated
    app.extensions["teacher_admin_elevation_68_registered"] = True
    return app
