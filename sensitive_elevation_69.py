"""Teacher 6.9 sensitive-operation elevation boundary.

Ordinary course/material/question/evaluation work is intentionally absent from
this module: those requests use session RBAC and group scope only.  Elevation
is an additional, short-lived check for operations with a materially larger
blast radius.
"""
from __future__ import annotations

from flask import jsonify, request

from teacher_app.common.auth import has_permission


# Permission tuples mean "any of these permissions may own this operation".
# Method/path rules avoid depending on legacy Flask endpoint names.
SENSITIVE_RULES = (
    ({"POST", "PUT", "PATCH", "DELETE"}, "/api/users", ("user.manage",)),
    ({"POST"}, "/api/storage/migrate-to-", ("storage.manage",)),
    ({"POST"}, "/api/maintenance/restore", ("backup.manage", "education.cross_group.manage")),
    ({"GET"}, "/api/maintenance/backup", ("backup.manage", "education.cross_group.manage")),
    ({"DELETE"}, "/api/records", ("system.manage",)),
)


def _required_permissions(method: str, path: str):
    method = str(method or "").upper()
    path = str(path or "")
    for methods, prefix, permissions in SENSITIVE_RULES:
        if method in methods and (path == prefix or path.startswith(prefix + "/") or prefix.endswith("-") and path.startswith(prefix)):
            return permissions
    return ()


def register_sensitive_elevation_69(base):
    app = base.app
    if app.extensions.get("teacher_sensitive_elevation_69_registered"):
        return app

    @app.before_request
    def sensitive_elevation_boundary():
        permissions = _required_permissions(request.method, request.path)
        if not permissions:
            return None

        user = base._current_user()
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not any(has_permission(user, permission) for permission in permissions):
            return jsonify({"error": "權限不足。"}), 403

        guard = getattr(base, "require_elevated_permission", None)
        if guard is None:
            # Fail closed if an unexpected deployment omitted the elevation
            # adapter; never silently downgrade a sensitive operation.
            return jsonify({
                "error": "敏感操作驗證服務尚未啟用。",
                "elevationRequired": True,
            }), 503
        return guard(*permissions)

    app.extensions["teacher_sensitive_elevation_69_registered"] = True
    return app
