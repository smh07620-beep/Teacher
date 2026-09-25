"""Authenticated learner course-feedback routes."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common.errors import ApiError
from teacher_app.learning import feedback_service


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


def register_course_feedback_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_course_feedback_routes_registered"):
        return app

    def api_course_feedback_get(course_id):
        try:
            return jsonify(feedback_service.get_own_feedback(_current_user(owner), course_id))
        except ApiError as exc:
            return _error(exc)

    def api_course_feedback_put(course_id):
        try:
            return jsonify(
                feedback_service.submit_feedback(
                    _current_user(owner),
                    course_id,
                    request.get_json(silent=True) or {},
                )
            )
        except ApiError as exc:
            return _error(exc)

    def api_course_feedback_summary(course_id):
        try:
            return jsonify(feedback_service.feedback_summary(_current_user(owner), course_id))
        except ApiError as exc:
            return _error(exc)

    _install(app, "/api/course-feedback/<course_id>", "api_course_feedback_get", ["GET"], api_course_feedback_get)
    _install(app, "/api/course-feedback/<course_id>", "api_course_feedback_put", ["PUT"], api_course_feedback_put)
    _install(
        app,
        "/api/course-feedback/<course_id>/summary",
        "api_course_feedback_summary",
        ["GET"],
        api_course_feedback_summary,
    )
    app.extensions["teacher_course_feedback_routes_registered"] = True
    return app


__all__ = ["register_course_feedback_routes"]
