"""Authenticated routes for cross-device saved learning items."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common.errors import ApiError
from teacher_app.learning import saved_service


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


def register_saved_learning_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_saved_learning_routes_registered"):
        return app

    def api_saved_learning_items():
        try:
            return jsonify({"items": saved_service.list_saved_items(_current_user(owner))})
        except ApiError as exc:
            return _error(exc)

    def api_saved_learning_item_update(item_type, item_id):
        data = request.get_json(silent=True) or {}
        if not isinstance(data.get("saved"), bool):
            return _error(ApiError("INVALID_SAVED_STATE", "saved 必須是布林值。", status=400))
        try:
            return jsonify(
                saved_service.set_saved_item(
                    _current_user(owner), item_type, item_id, saved=data["saved"]
                )
            )
        except ApiError as exc:
            return _error(exc)

    _install(app, "/api/saved-learning-items", "api_saved_learning_items", ["GET"], api_saved_learning_items)
    _install(
        app,
        "/api/saved-learning-items/<item_type>/<item_id>",
        "api_saved_learning_item_update",
        ["PUT"],
        api_saved_learning_item_update,
    )
    app.extensions["teacher_saved_learning_routes_registered"] = True
    return app


__all__ = ["register_saved_learning_routes"]
