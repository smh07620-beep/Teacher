"""Authenticated read-only learning calendar route."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common.errors import ApiError
from teacher_app.learning import calendar_service


def _current_user(owner=None):
    if hasattr(g, "teacher_user"):
        return g.teacher_user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def register_learning_calendar_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_learning_calendar_routes_registered"):
        return app

    def api_learning_calendar():
        try:
            try:
                days = int(request.args.get("days", 90))
            except (TypeError, ValueError):
                raise ApiError("INVALID_CALENDAR_RANGE", "行事曆天數格式不正確。", status=400)
            return jsonify(calendar_service.calendar_summary(_current_user(owner), days=days))
        except ApiError as exc:
            body = {"error": exc.message, "code": exc.code}
            body.update(exc.extra)
            return jsonify(body), exc.status

    app.add_url_rule("/api/learning-calendar", endpoint="api_learning_calendar", view_func=api_learning_calendar, methods=["GET"])
    app.extensions["teacher_learning_calendar_routes_registered"] = True
    return app


__all__ = ["register_learning_calendar_routes"]
