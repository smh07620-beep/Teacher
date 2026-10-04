"""HTTP routes for F3 training intervention cases."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common.errors import ApiError
from teacher_app.learning import intervention_service


def _current_user(owner=None):
    user = getattr(g, "teacher_user", None)
    if user is not None:
        return user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _error(exc: ApiError):
    body = {"error": exc.message, "code": exc.code}
    body.update(exc.extra or {})
    return jsonify(body), exc.status


def register_training_intervention_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_training_intervention_routes_registered"):
        return app

    @app.get("/api/training-interventions")
    def api_training_interventions():
        try:
            return jsonify(
                intervention_service.manager_list(
                    _current_user(owner),
                    area=request.args.get("area", ""),
                    group=request.args.get("group", ""),
                    course_id=request.args.get("courseId", ""),
                    status=request.args.get("status", ""),
                )
            )
        except ApiError as exc:
            return _error(exc)

    @app.post("/api/training-interventions")
    def api_training_intervention_create():
        try:
            result = intervention_service.create_or_refresh(
                _current_user(owner),
                request.get_json(silent=True) or {},
            )
            return jsonify(result), 201 if result.get("created") else 200
        except ApiError as exc:
            return _error(exc)

    @app.patch("/api/training-interventions/<intervention_id>")
    def api_training_intervention_update(intervention_id):
        try:
            return jsonify(
                intervention_service.update_case(
                    _current_user(owner),
                    intervention_id,
                    request.get_json(silent=True) or {},
                )
            )
        except ApiError as exc:
            return _error(exc)

    @app.get("/api/training-interventions/mine")
    def api_training_interventions_mine():
        try:
            return jsonify(
                intervention_service.mine(
                    _current_user(owner),
                    include_closed=request.args.get("includeClosed", "").lower()
                    in {"1", "true", "yes"},
                )
            )
        except ApiError as exc:
            return _error(exc)

    app.extensions["teacher_training_intervention_routes_registered"] = True
    return app


__all__ = ["register_training_intervention_routes"]
