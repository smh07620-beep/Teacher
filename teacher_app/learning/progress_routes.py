"""Canonical HTTP adapters for legacy learner completion/progress URLs."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common import scope
from teacher_app.learning import progress_service


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


def _current_user_or_error(owner=None):
    user = _current_user(owner)
    if not user:
        return None, (
            jsonify({"error": "請先登入後再使用教材。", "loginRequired": True}),
            401,
        )
    return user, None


def register_progress_routes(owner):
    app = _app(owner)
    if app.extensions.get("teacher_progress_routes_registered"):
        return app

    def api_material_progress():
        user, denied = _current_user_or_error(owner)
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        try:
            completed_at = progress_service.mark_material_complete(
                user,
                data.get("materialId", ""),
            )
        except progress_service.ProgressError as exc:
            return jsonify({"error": str(exc)}), exc.status
        return jsonify({"ok": True, "completedAt": completed_at})

    def api_my_progress():
        user, denied = _current_user_or_error(owner)
        if denied:
            return denied
        try:
            payload = progress_service.my_progress(
                user,
                area=request.args.get("area", "pgy"),
                group=request.args.get("group", scope.DEFAULT_GROUP),
            )
        except progress_service.ProgressError as exc:
            return jsonify({"error": str(exc)}), exc.status
        return jsonify(payload)

    _install(
        app,
        "/api/material-progress",
        "api_material_progress",
        ["POST"],
        api_material_progress,
    )
    _install(
        app,
        "/api/my-progress",
        "api_my_progress",
        ["GET"],
        api_my_progress,
    )
    app.extensions["teacher_progress_routes_registered"] = True
    return app


__all__ = ["register_progress_routes"]
