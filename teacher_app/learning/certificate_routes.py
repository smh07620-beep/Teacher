"""Authenticated learner routes for course completion certificates."""
from __future__ import annotations

from flask import g, jsonify

from teacher_app.common.errors import ApiError
from teacher_app.learning import certificate_service


def _install(app, rule: str, endpoint: str, methods: list[str], view_func) -> None:
    if endpoint in app.view_functions:
        app.view_functions[endpoint] = view_func
        return
    app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=methods)


def _current_user(owner=None):
    if hasattr(g, "teacher_user"):
        return g.teacher_user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _error(exc: ApiError):
    body = {"error": exc.message, "code": exc.code}
    body.update(exc.extra)
    return jsonify(body), exc.status


def register_completion_certificate_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_completion_certificate_routes_registered"):
        return app

    def api_completion_certificates():
        try:
            return jsonify({"items": certificate_service.list_certificates(_current_user(owner))})
        except ApiError as exc:
            return _error(exc)

    def api_issue_completion_certificate(course_id):
        try:
            return jsonify(certificate_service.issue_certificate(_current_user(owner), course_id))
        except ApiError as exc:
            return _error(exc)

    def api_completion_certificate(certificate_id):
        try:
            return jsonify({"certificate": certificate_service.get_certificate(_current_user(owner), certificate_id)})
        except ApiError as exc:
            return _error(exc)

    _install(app, "/api/completion-certificates", "api_completion_certificates", ["GET"], api_completion_certificates)
    _install(
        app,
        "/api/completion-certificates/<course_id>",
        "api_issue_completion_certificate",
        ["POST"],
        api_issue_completion_certificate,
    )
    _install(
        app,
        "/api/completion-certificates/id/<certificate_id>",
        "api_completion_certificate",
        ["GET"],
        api_completion_certificate,
    )
    app.extensions["teacher_completion_certificate_routes_registered"] = True
    return app


__all__ = ["register_completion_certificate_routes"]
