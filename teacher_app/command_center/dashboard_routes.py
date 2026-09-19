"""Canonical HTTP compatibility route for the personalized dashboard."""
from __future__ import annotations

from flask import g, jsonify

from teacher_app.command_center import dashboard_service


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


def register_dashboard_routes(owner):
    app = _app(owner)
    if app.extensions.get("teacher_dashboard_routes_registered"):
        return app

    def api_dashboard_me():
        user = _current_user(owner)
        if not user:
            return jsonify(
                {"error": "請先登入後再使用教材。", "loginRequired": True}
            ), 401
        return jsonify(dashboard_service.dashboard_summary(user))

    _install(
        app,
        "/api/dashboard/me",
        "api_dashboard_me",
        ["GET"],
        api_dashboard_me,
    )
    app.extensions["teacher_dashboard_routes_registered"] = True
    return app


__all__ = ["register_dashboard_routes"]
