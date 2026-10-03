"""Authenticated read-state and email-preference routes for notifications."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.auth import repository as auth_repository
from teacher_app.command_center import notification_state
from teacher_app.common import audit
from teacher_app.common.auth import has_role, require_role
from teacher_app.common.errors import ApiError
from teacher_app.notifications import incidents, preferences
from teacher_app.operations import history as operational_history


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

    def api_operational_metrics():
        actor = _current_user(owner)
        try:
            require_role(actor, "system_admin")
            requested = str(request.args.get("window") or "24h").strip().lower()
            window = "7d" if requested == "7d" else "24h"
            return jsonify(operational_history.build_operational_dashboard(window=window))
        except ApiError as exc:
            return _error(exc)

    def api_operational_incident_responders():
        actor = _current_user(owner)
        try:
            require_role(actor, "system_admin")
            responders = []
            for row in auth_repository.list_users():
                if not row.get("active") or not has_role(row, "system_admin"):
                    continue
                responders.append({
                    "username": str(row.get("username") or "")[:100],
                    "name": str(row.get("display_name") or row.get("username") or "")[:100],
                })
            return jsonify({"responders": responders})
        except ApiError as exc:
            return _error(exc)

    def api_operational_incident_update(incident_key):
        actor = _current_user(owner)
        try:
            require_role(actor, "system_admin")
            data = request.get_json(silent=True) or {}
            action = str(data.get("action") or "").strip().lower()
            assigned_to = str(data.get("assignedTo") or "").strip()[:100]
            if action == "assign":
                assignee = auth_repository.find_user(assigned_to)
                if (
                    not assignee
                    or not assignee.get("active")
                    or not has_role(assignee, "system_admin")
                ):
                    raise ApiError(
                        "INVALID_INCIDENT_ASSIGNEE",
                        "Incident 只能指派給啟用中的系統管理者。",
                        status=400,
                    )
            try:
                maintenance_minutes = int(data.get("maintenanceMinutes") or 60)
            except (TypeError, ValueError):
                raise ApiError(
                    "INVALID_INCIDENT_MAINTENANCE",
                    "維護時間格式不正確。",
                    status=400,
                )
            if action == "maintenance" and not 15 <= maintenance_minutes <= 1440:
                raise ApiError(
                    "INVALID_INCIDENT_MAINTENANCE",
                    "維護時間需介於 15 分鐘至 24 小時。",
                    status=400,
                )
            try:
                result = incidents.update_incident_response(
                    incident_key,
                    actor_username=str((actor or {}).get("username") or ""),
                    action=action,
                    assigned_to=assigned_to,
                    maintenance_minutes=maintenance_minutes,
                    note=str(data.get("note") or ""),
                )
            except ValueError as exc:
                raise ApiError(
                    "INVALID_INCIDENT_RESPONSE",
                    str(exc),
                    status=409,
                )
            if not result:
                raise ApiError(
                    "INCIDENT_NOT_FOUND",
                    "找不到此維運 Incident。",
                    status=404,
                )
            audit.record_event(
                actor=actor,
                action=f"operational.incident.{action}",
                target_type="operational_incident",
                target_id=str(result.get("incidentKey") or "")[:180],
                after={
                    "status": result.get("status"),
                    "responseState": result.get("responseState"),
                    "assignedTo": result.get("assignedTo"),
                    "maintenanceUntil": result.get("maintenanceUntil"),
                },
                detail={
                    "generation": result.get("generation"),
                    "errorCode": result.get("errorCode"),
                    "note": str(data.get("note") or "")[:1000],
                },
            )
            return jsonify({"ok": True, "incident": result})
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
    _install(
        app,
        "/api/operational-metrics",
        "api_operational_metrics",
        ["GET"],
        api_operational_metrics,
    )
    _install(
        app,
        "/api/operational-incidents/responders",
        "api_operational_incident_responders",
        ["GET"],
        api_operational_incident_responders,
    )
    _install(
        app,
        "/api/operational-incidents/<path:incident_key>",
        "api_operational_incident_update",
        ["PATCH"],
        api_operational_incident_update,
    )
    app.extensions["teacher_notification_state_routes_registered"] = True
    return app


__all__ = ["register_notification_state_routes"]
