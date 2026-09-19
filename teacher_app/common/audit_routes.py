"""Read-only HTTP surface for canonical non-PGY audit events."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common import audit
from teacher_app.common.auth import has_permission


def _actor(owner=None):
    user = getattr(g, "teacher_user", None)
    if user is not None:
        return user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def register_general_audit_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_general_audit_routes_registered"):
        return app

    @app.get("/api/audit/events")
    def general_audit_events():
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not has_permission(user, "audit.read"):
            return jsonify({"error": "權限不足。"}), 403
        try:
            limit = int(request.args.get("limit", 200) or 200)
        except (TypeError, ValueError):
            limit = 200
        items = audit.list_events(
            limit=limit,
            action=request.args.get("action", ""),
            target_type=request.args.get("targetType", ""),
            target_id=request.args.get("targetId", ""),
            group=request.args.get("group", ""),
        )
        return jsonify({"items": items, "count": len(items)})

    app.extensions["teacher_general_audit_routes_registered"] = True
    return app


__all__ = ["register_general_audit_routes"]
