"""Canonical registration façade for legacy RBAC compatibility boundaries."""
from __future__ import annotations

from flask import g, jsonify

from teacher_app.auth import repository as auth_repository
from teacher_app.auth import rbac_legacy_adapter
from teacher_app.auth.service import public_user
from teacher_app.common import scope_filter
from teacher_app.common.auth import is_teacher_workspace_user
from teacher_app.frontend import system_page


OFFICE_EXTENSIONS = system_page.OFFICE_EXTENSIONS
GROUP_SCOPED_ROLES = scope_filter.GROUP_SCOPED_ROLES
GROUP_SCOPED_PERMISSIONS = scope_filter.GROUP_SCOPED_PERMISSIONS
LEGACY_ENDPOINT_POLICIES = rbac_legacy_adapter.LEGACY_ENDPOINT_POLICIES
DEFAULT_GROUP_ENDPOINTS = scope_filter.DEFAULT_GROUP_ENDPOINTS
FILTERED_LIST_ENDPOINTS = scope_filter.FILTERED_LIST_ENDPOINTS

_denied = scope_filter.denied
_preferred_group = scope_filter.preferred_group
_row_group = scope_filter.row_group
_json_object = scope_filter.json_object
_category_group = scope_filter.category_group
_question_group = scope_filter.question_group
_upload_session_group = scope_filter.upload_session_group
_blueprint_group = scope_filter.blueprint_group
_request_groups = scope_filter.request_groups
_scoped_groups = scope_filter.scoped_groups
_scoped = scope_filter.scoped
_admin_key_override = rbac_legacy_adapter.admin_key_override
_legacy_admin_guard = rbac_legacy_adapter.legacy_admin_guard
_require_permission = scope_filter.require_permission
_require_any_permission = scope_filter.require_any_permission
_item_group = scope_filter.item_group
_filter_items = scope_filter.filter_items
_filter_scoped_response = scope_filter.filter_scoped_response
_ensure_07620 = rbac_legacy_adapter.ensure_07620


def _register_profile_route(app) -> None:
    if "current_profile" in app.view_functions:
        return

    def current_profile():
        user = getattr(g, "teacher_user", None)
        if not user:
            return jsonify({"authenticated": False, "user": None})
        row = auth_repository.find_user(user["username"])
        return jsonify({
            "authenticated": bool(row),
            "user": public_user(row, include_roles=True) if row else None,
        })

    app.add_url_rule(
        "/api/auth/profile",
        endpoint="current_profile",
        view_func=current_profile,
        methods=["GET"],
    )


def _install_app_guards(app) -> dict:
    guards = {
        "require_admin": lambda: rbac_legacy_adapter.legacy_admin_guard(app),
        "require_permission": lambda permission: scope_filter.require_permission(app, permission),
        "require_any_permission": lambda *permissions: scope_filter.require_any_permission(app, *permissions),
        "require_system_admin": lambda: scope_filter.denied(app, "system.manage")[1],
        "require_teacher_workspace": lambda: (
            None
            if (
                getattr(g, "teacher_user", None)
                and is_teacher_workspace_user(g.teacher_user)
            )
            else (jsonify({"error": "教師工作區權限不足。"}), 403)
        ),
        "require_scoped_permission": lambda permission, group=None: scope_filter.scoped(
            app,
            permission,
            group,
        )[1],
    }
    app.extensions["teacher_rbac_guards"] = guards
    return guards


def _install_compat_owner_guards(compat_owner, guards: dict) -> None:
    compat_owner.require_admin = guards["require_admin"]
    compat_owner.require_permission = guards["require_permission"]
    compat_owner.require_any_permission = guards["require_any_permission"]
    compat_owner.require_system_admin = guards["require_system_admin"]
    compat_owner.require_teacher_workspace = guards["require_teacher_workspace"]
    compat_owner.require_scoped_permission = guards["require_scoped_permission"]


def register_rbac_681(owner, *, compat_owner=None):
    app = getattr(owner, "app", owner)
    if compat_owner is None and owner is not app:
        compat_owner = owner
    if app.extensions.get("teacher_rbac_681_registered"):
        if compat_owner is not None:
            _install_compat_owner_guards(
                compat_owner,
                app.extensions["teacher_rbac_guards"],
            )
        return app

    _register_profile_route(app)
    guards = _install_app_guards(app)
    if compat_owner is not None:
        _install_compat_owner_guards(compat_owner, guards)
    scope_filter.register_scope_filter(app)
    system_page.register_system_page(app)
    app.extensions["teacher_rbac_681_registered"] = True
    return app


__all__ = [
    "DEFAULT_GROUP_ENDPOINTS",
    "FILTERED_LIST_ENDPOINTS",
    "GROUP_SCOPED_PERMISSIONS",
    "GROUP_SCOPED_ROLES",
    "LEGACY_ENDPOINT_POLICIES",
    "OFFICE_EXTENSIONS",
    "register_rbac_681",
]
