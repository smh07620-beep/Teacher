"""Canonical HTTP compatibility routes for platform announcements."""
from __future__ import annotations

import hmac
import os

from flask import g, jsonify, request

from teacher_app.common.auth import has_permission
from teacher_app.maintenance import announcement_service


def _install(app, rule: str, endpoint: str, methods: list[str], view_func) -> None:
    if endpoint in app.view_functions:
        app.view_functions[endpoint] = view_func
        return
    app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=methods)


def _app(owner):
    return getattr(owner, "app", owner)


def _current_user(owner=None):
    if hasattr(g, "teacher_user"):
        return g.teacher_user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _require_admin(owner=None):
    supplied = str(request.headers.get("X-Admin-Key", "") or "")
    admin_key = os.environ.get("ADMIN_KEY", "").strip()
    if admin_key and supplied and hmac.compare_digest(supplied, admin_key):
        return None
    user = _current_user(owner)
    if not user:
        return jsonify({
            "error": "請先以管理者帳號登入，或提供正確的 ADMIN_KEY。",
            "loginRequired": True,
        }), 401
    if not (
        has_permission(user, "user.manage")
        or has_permission(user, "system.manage")
    ):
        return jsonify({"error": "權限不足：此功能限教學管理者使用。"}), 403
    return None


def register_announcement_routes(owner):
    app = _app(owner)
    if app.extensions.get("teacher_announcement_routes_registered"):
        return app

    def api_announcements_public():
        try:
            limit = max(1, min(50, int(request.args.get("limit", "8"))))
        except (TypeError, ValueError):
            limit = 8
        return jsonify(announcement_service.list_public(limit))

    def api_announcements_admin():
        denied = _require_admin(owner)
        if denied:
            return denied
        return jsonify(announcement_service.list_admin())

    def api_announcements_create():
        denied = _require_admin(owner)
        if denied:
            return denied
        try:
            item = announcement_service.create(request.get_json(silent=True) or {})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(item), 201

    def api_announcements_update(announcement_id):
        denied = _require_admin(owner)
        if denied:
            return denied
        try:
            item = announcement_service.update(
                announcement_id,
                request.get_json(silent=True) or {},
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if item is None:
            return jsonify({"error": "找不到公告"}), 404
        return jsonify(item)

    def api_announcements_delete(announcement_id):
        denied = _require_admin(owner)
        if denied:
            return denied
        if not announcement_service.delete(announcement_id):
            return jsonify({"error": "找不到公告"}), 404
        return jsonify({"ok": True})

    _install(app, "/api/announcements", "api_announcements_public", ["GET"], api_announcements_public)
    _install(app, "/api/announcements/admin", "api_announcements_admin", ["GET"], api_announcements_admin)
    _install(app, "/api/announcements", "api_announcements_create", ["POST"], api_announcements_create)
    _install(
        app,
        "/api/announcements/<announcement_id>",
        "api_announcements_update",
        ["PATCH"],
        api_announcements_update,
    )
    _install(
        app,
        "/api/announcements/<announcement_id>",
        "api_announcements_delete",
        ["DELETE"],
        api_announcements_delete,
    )
    app.extensions["teacher_announcement_routes_registered"] = True
    return app


__all__ = ["register_announcement_routes"]
