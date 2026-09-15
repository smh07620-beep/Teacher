"""Teacher 6.8.1 capability and workspace consolidation.

Normal requests authenticate with the session and are authorized by canonical
roles, capabilities, and a conservative group scope.  ``ADMIN_KEY`` remains
only in the legacy elevation endpoint as an emergency recovery compatibility
path; this module never reads it.
"""
from __future__ import annotations

import json
from pathlib import Path

from flask import abort, jsonify, redirect, request, send_from_directory

from teacher_app.common.auth import (
    has_permission,
    has_role,
    is_system_admin,
    is_teacher_workspace_user,
    normalize_roles,
)
from teacher_app.auth.service import public_user

OFFICE_EXTENSIONS = {".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx", ".odp", ".odt", ".ods"}
TEACHER_ROLES = {"clinical_teacher", "group_leader", "education_admin", "system_admin"}


def _denied(base, *permissions):
    user = base._current_user()
    if not user:
        return None, (jsonify({"error": "請先登入。", "loginRequired": True}), 401)
    if not any(has_permission(user, permission) for permission in permissions):
        return None, (jsonify({"error": "權限不足。"}), 403)
    return user, None


def _scoped(base, permission, group=None):
    user, denied = _denied(base, permission)
    if denied:
        return None, denied
    if is_system_admin(user) or has_role(user, "education_admin"):
        return user, None
    # Scope data is intentionally conservative: no group/assignment means no
    # inferred write permission.  Preferred group is the existing account
    # assignment seam used by the legacy course/material records.
    if has_role(user, "group_leader") or has_role(user, "clinical_teacher"):
        if group and str(user.get("preferredGroup") or "") == str(group):
            return user, None
        return None, (jsonify({"error": "此資源不在你的授權範圍。"}), 403)
    return None, (jsonify({"error": "權限不足。"}), 403)


def _ensure_07620(base):
    """Idempotently add system_admin to the known account without touching auth."""
    conn, kind = base._db_conn()
    ph = "%s" if kind == "postgres" else "?"
    try:
        row = conn.execute(f"SELECT username, role, roles_json FROM user_accounts WHERE username={ph}", ("07620",)).fetchone()
        if not row:
            base.app.logger.warning("RBAC compatibility: account 07620 is absent; no account was created.")
            return False
        data = dict(row)
        roles = normalize_roles(data.get("roles_json"), primary=data.get("role"))
        if "system_admin" in roles and data.get("role") == "system_admin":
            return True
        roles = ["system_admin"] + [role for role in roles if role != "system_admin"]
        conn.execute(
            f"UPDATE user_accounts SET role={ph}, roles_json={ph} WHERE username={ph}",
            ("system_admin", json.dumps(roles, ensure_ascii=False, separators=(",", ":")), "07620"),
        )
        return True
    finally:
        conn.close()


def register_rbac_681(base):
    app = base.app
    if app.extensions.get("teacher_rbac_681_registered"):
        return app

    _ensure_07620(base)

    @app.get("/api/auth/profile")
    def current_profile():
        user = base._current_user()
        if not user:
            return jsonify({"authenticated": False, "user": None})
        conn, kind = base._db_conn()
        ph = "%s" if kind == "postgres" else "?"
        try:
            row = conn.execute(f"SELECT * FROM user_accounts WHERE username={ph}", (user["username"],)).fetchone()
            return jsonify({"authenticated": bool(row), "user": public_user(base, row, include_roles=True) if row else None})
        finally:
            conn.close()

    # Public helpers are intentionally response-shaped for legacy routes.
    base.require_permission = lambda permission: _denied(base, permission)[1]
    base.require_any_permission = lambda *permissions: _denied(base, *permissions)[1]
    base.require_system_admin = lambda: _denied(base, "system.manage")[1]
    base.require_teacher_workspace = lambda: (
        None if (base._current_user() and is_teacher_workspace_user(base._current_user()))
        else (jsonify({"error": "教師工作區權限不足。"}), 403)
    )
    base.require_scoped_permission = lambda permission, group=None: _scoped(base, permission, group)[1]

    # ``/system`` is the learner shell.  Its management mode is a distinct
    # protected workspace rather than an ADMIN_KEY query-string escape hatch.
    def system_page():
        user = base._current_user()
        if not user:
            return redirect("/login?next=/system")
        if request.args.get("admin") == "1" and not is_teacher_workspace_user(user):
            return jsonify({"error": "學生不能進入管理區。"}), 403
        return send_from_directory(base.STATIC_DIR, "system.html")

    for rule in app.url_map.iter_rules():
        if rule.rule == "/system" and "GET" in rule.methods:
            app.view_functions[rule.endpoint] = system_page

    # Defense in depth: a malformed legacy viewerMode can never turn an
    # Office source into an inline/download response for a learner.
    def learner_office_view(material_id):
        entry = base.get_material(material_id)
        if not entry or not entry.get("active"):
            abort(404)
        user = base._current_user()
        extension = Path(str(entry.get("filename") or "")).suffix.lower()
        if extension in OFFICE_EXTENSIONS and has_role(user, "student"):
            meta = entry.get("storageMeta") or {}
            if meta.get("previewMode") == "single_pdf":
                return redirect(f"/material-preview/{material_id}", code=302)
            return jsonify({"error": "教材預覽尚未完成，請管理者重新處理。", "previewRequired": True}), 409
        # Non-learner original access remains explicitly capability gated.
        if extension in OFFICE_EXTENSIONS and not has_permission(user, "material.manage"):
            return jsonify({"error": "權限不足。"}), 403
        return app.extensions["teacher_legacy_view_material"](material_id)

    for rule in app.url_map.iter_rules():
        if rule.rule == "/view/<material_id>" and "GET" in rule.methods:
            app.extensions["teacher_legacy_view_material"] = app.view_functions[rule.endpoint]
            app.view_functions[rule.endpoint] = learner_office_view

    app.extensions["teacher_rbac_681_registered"] = True
    return app
