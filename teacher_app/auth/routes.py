"""Auth HTTP adapters preserving the exact legacy URL and JSON contract."""

from flask import jsonify, request, session

from teacher_app.auth import bp, service
from teacher_app.common.auth import require_role
from teacher_app.common.errors import ApiError


def legacy_error(exc):
    body = {"error": exc.message}
    body.update(exc.extra)
    if exc.code == "LOGIN_REQUIRED":
        body["loginRequired"] = True
    return jsonify(body), exc.status


@bp.get("/api/auth/me")
def me():
    user = service.current_user(session)
    return jsonify({"authenticated": bool(user), "user": user})


@bp.post("/api/auth/login")
def login():
    try:
        return jsonify(service.login(request.get_json(silent=True) or {}, session))
    except ApiError as exc:
        return legacy_error(exc)


@bp.post("/api/auth/logout")
def logout():
    return jsonify(service.logout(session))


def require_roles(user, *allowed_roles):
    """Translate centralized RBAC errors to the legacy (user, denied) seam."""
    try:
        return require_role(user, *allowed_roles), None
    except ApiError as exc:
        return None, legacy_error(exc)
