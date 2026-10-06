"""Canonical HTTP routes for scoped teaching and system announcements."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common.auth import has_permission, has_role
from teacher_app.common import scope_filter
from teacher_app.courses import repository as course_repository
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


def _login_denied():
    return jsonify({
        "error": "請先以管理者帳號登入。",
        "loginRequired": True,
    }), 401


def _permission_denied():
    return jsonify({"error": "權限不足：此功能限教學管理者使用。"}), 403


def _require_admin(owner=None):
    """Compatibility guard for retained system-admin boundary tests/callers."""
    return _require_kind(_current_user(owner), "system")


def _kind_for(user, payload) -> str:
    requested = str((payload or {}).get("kind") or "").strip().lower()
    if requested:
        return requested
    return "system" if has_permission(user, "system.manage") else "teaching"


def _require_kind(user, kind: str):
    if not user:
        return _login_denied()
    if kind == "system":
        return None if has_permission(user, "system.manage") else _permission_denied()
    if kind == "teaching":
        return None if has_permission(user, "announcement.manage") else _permission_denied()
    return jsonify({"error": "公告類型不正確"}), 400


def _preferred_area(user) -> str:
    return str(
        (user or {}).get("preferredArea")
        or (user or {}).get("preferred_area")
        or ""
    ).strip()


def _scope_payload(user, payload, *, existing=None):
    """Return a server-scoped payload or an authorization response.

    Clinical teachers and group leaders may only manage their own group/course.
    Education/system administrators retain cross-group teaching scope. System
    announcements are always global and system-admin only.
    """
    data = dict(payload or {})
    existing = dict(existing or {})
    kind = str(data.get("kind") or existing.get("kind") or "teaching").strip().lower()
    data["kind"] = kind

    if kind == "system":
        data.update({"scopeType": "all", "area": "", "group": "", "courseId": ""})
        return data, None

    if not scope_filter.is_group_scoped_actor(user):
        return data, None

    own_group = scope_filter.preferred_group(user)
    if not own_group:
        return None, (jsonify({"error": "此帳號尚未設定可管理的組別範圍。"}), 403)

    scope_type = str(
        data.get("scopeType")
        or existing.get("scopeType")
        or "group"
    ).strip().lower()

    if scope_type == "all":
        return None, (jsonify({"error": "此帳號只能發布自己組別或組內課程公告。"}), 403)

    if scope_type == "course":
        course_id = str(data.get("courseId") or existing.get("courseId") or "").strip()
        course = course_repository.get_course(course_id) if course_id else None
        if not course:
            return None, (jsonify({"error": "找不到公告指定的課程。"}), 400)
        if str(course.get("group") or "") != own_group:
            return None, (jsonify({"error": "此課程不在你的授權範圍。"}), 403)
        data["courseId"] = course_id
        data["group"] = own_group
        data["area"] = str(course.get("area") or _preferred_area(user))
        data["scopeType"] = "course"
        return data, None

    requested_group = str(data.get("group") or existing.get("group") or own_group).strip()
    if requested_group != own_group:
        return None, (jsonify({"error": "此組別不在你的授權範圍。"}), 403)
    data["scopeType"] = "group"
    data["group"] = own_group
    data["area"] = str(data.get("area") or existing.get("area") or _preferred_area(user)).strip()
    data["courseId"] = ""
    return data, None


def _can_manage_existing(user, item):
    kind = str((item or {}).get("kind") or "system")
    denied = _require_kind(user, kind)
    if denied:
        return denied
    if kind != "teaching":
        return None
    if not scope_filter.is_group_scoped_actor(user):
        return None
    own_group = scope_filter.preferred_group(user)
    if not own_group or str((item or {}).get("group") or "") != own_group:
        return jsonify({"error": "此公告不在你的授權範圍。"}), 403
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
        return jsonify(
            announcement_service.list_public(
                limit,
                user=_current_user(owner),
            )
        )

    def api_announcements_admin():
        user = _current_user(owner)
        if not user:
            return _login_denied()

        requested_kind = str(request.args.get("kind") or "").strip().lower()
        if requested_kind:
            denied = _require_kind(user, requested_kind)
            if denied:
                return denied
            kind = requested_kind
        elif has_permission(user, "system.manage"):
            # Compatibility: historical system-admin callers saw both kinds.
            kind = ""
        elif has_permission(user, "announcement.manage"):
            kind = "teaching"
        else:
            return _permission_denied()

        group = ""
        if kind != "system" and scope_filter.is_group_scoped_actor(user):
            group = scope_filter.preferred_group(user)
            if not group:
                return jsonify({"error": "此帳號尚未設定可管理的組別範圍。"}), 403
        return jsonify(announcement_service.list_admin(kind=kind, group=group))

    def api_announcements_create():
        user = _current_user(owner)
        if not user:
            return _login_denied()
        raw = dict(request.get_json(silent=True) or {})
        kind = _kind_for(user, raw)
        denied = _require_kind(user, kind)
        if denied:
            return denied
        raw["kind"] = kind
        raw["createdBy"] = str(user.get("username") or "")
        scoped, denied = _scope_payload(user, raw)
        if denied:
            return denied
        try:
            item = announcement_service.create(scoped)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(item), 201

    def api_announcements_update(announcement_id):
        user = _current_user(owner)
        if not user:
            return _login_denied()
        existing = announcement_service.get(announcement_id)
        if existing is None:
            return jsonify({"error": "找不到公告"}), 404
        denied = _can_manage_existing(user, existing)
        if denied:
            return denied

        raw = dict(request.get_json(silent=True) or {})
        # Announcement class/creator cannot be changed through an edit.
        raw["kind"] = existing.get("kind") or "system"
        raw.pop("createdBy", None)
        scoped, denied = _scope_payload(user, raw, existing=existing)
        if denied:
            return denied
        try:
            item = announcement_service.update(announcement_id, scoped)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if item is None:
            return jsonify({"error": "找不到公告"}), 404
        return jsonify(item)

    def api_announcements_delete(announcement_id):
        user = _current_user(owner)
        if not user:
            return _login_denied()
        existing = announcement_service.get(announcement_id)
        if existing is None:
            return jsonify({"error": "找不到公告"}), 404
        denied = _can_manage_existing(user, existing)
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
