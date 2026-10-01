"""Authenticated read-state and email-preference routes for notifications."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.command_center import notification_state
from teacher_app.common import audit
from teacher_app.common.errors import ApiError
from teacher_app.notifications import preferences


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


def register_notification_state_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_notification_state_routes_registered"):
        return app

    def api_notification_states():
        try:
            states = notification_state.list_states(
                _current_user(owner),
                request.args.getlist("key"),
            )
            return jsonify({"states": states})
        except ApiError as exc:
            return _error(exc)

    def api_notification_states_update():
        data = request.get_json(silent=True) or {}
        try:
            keys = data.get("keys")
            read = data.get("read", True)
            if not isinstance(keys, list):
                raise ApiError(
                    "INVALID_NOTIFICATION_KEYS",
                    "通知識別碼必須以陣列提供。",
                    status=400,
                )
            if not isinstance(read, bool):
                raise ApiError(
                    "INVALID_NOTIFICATION_READ_STATE",
                    "通知已讀狀態必須是布林值。",
                    status=400,
                )
            states = notification_state.set_read_state(
                _current_user(owner),
                keys,
                read=read,
            )
            return jsonify({"ok": True, "states": states})
        except ApiError as exc:
            return _error(exc)

    def api_notification_preferences():
        try:
            return jsonify(preferences.get_preferences(_current_user(owner)))
        except ApiError as exc:
            return _error(exc)

    def api_notification_preferences_update():
        actor = _current_user(owner)
        try:
            result = preferences.update_preferences(actor, request.get_json(silent=True) or {})
            audit.record_event(
                actor=actor,
                action="notification.preferences.update",
                target_type="account",
                target_id=str((actor or {}).get("username") or ""),
                detail={"emailCategories": result["emailCategories"]},
            )
            return jsonify({"ok": True, **result})
        except ApiError as exc:
            return _error(exc)

    _install(
        app,
        "/api/notification-states",
        "api_notification_states",
        ["GET"],
        api_notification_states,
    )
    _install(
        app,
        "/api/notification-states",
        "api_notification_states_update",
        ["PATCH"],
        api_notification_states_update,
    )
    _install(
        app,
        "/api/notification-preferences",
        "api_notification_preferences",
        ["GET"],
        api_notification_preferences,
    )
    _install(
        app,
        "/api/notification-preferences",
        "api_notification_preferences_update",
        ["PATCH"],
        api_notification_preferences_update,
    )
    app.extensions["teacher_notification_state_routes_registered"] = True
    return app


__all__ = ["register_notification_state_routes"]
