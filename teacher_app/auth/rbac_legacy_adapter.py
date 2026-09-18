"""Compatibility translation from legacy admin guards to capability RBAC."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.auth import repository as auth_repository
from teacher_app.auth.service import public_user
from teacher_app.common.auth import has_permission, is_teacher_workspace_user
from teacher_app.common import scope_filter
from teacher_app.config import admin_key
from teacher_app.maintenance import account_roles


LEGACY_ENDPOINT_POLICIES = {
    "api_admin_slides": ("material.manage", "list"),
    "download_slide": ("material.manage", "scoped"),
    "api_upload_progress": ("material.manage", "capability"),
    "api_list_material_jobs": ("material.manage", "list"),
    "api_get_material_job": ("material.manage", "scoped"),
    "api_enqueue_material_job": ("material.manage", "scoped"),
    "api_retry_material_job": ("material.manage", "scoped"),
    "api_cancel_material_job": ("material.manage", "scoped"),
    "api_upload_slide": ("material.manage", "scoped"),
    "api_update_slide": ("material.manage", "scoped"),
    "api_delete_slide": ("material.manage", "scoped"),
    "material_upload_init": ("material.manage", "scoped"),
    "material_upload_complete": ("material.manage", "scoped"),
    "material_upload_abort": ("material.manage", "scoped"),
    "material_index": ("material.manage", "scoped"),
    "docx_atlas_preview": ("material.manage", "scoped"),
    "media_capability": ("material.manage", "capability"),
    "learning_analytics": ("result.group.read", "list"),
    "api_courses_admin": ("course.manage", "list"),
    "api_create_course": ("course.manage", "scoped"),
    "api_update_course": ("course.manage", "scoped"),
    "api_delete_course": ("course.manage", "scoped"),
    "api_get_teaching_plan": ("course.manage", "scoped"),
    "api_save_teaching_plan": ("course.manage", "scoped"),
    "api_ai_question_status": ("question.manage", "capability"),
    "api_ai_generate_questions": ("question.manage", "scoped"),
    "api_ai_import_questions": ("question.manage", "scoped"),
    "api_admin_list_quiz_categories": ("question.manage", "list"),
    "api_create_quiz_category": ("question.manage", "scoped"),
    "api_update_quiz_category": ("question.manage", "scoped"),
    "api_review_quiz_category": ("question.review", "scoped"),
    "api_quiz_publications": ("exam.manage", "scoped"),
    "api_publish_quiz_category": ("exam.publish", "scoped"),
    "api_delete_quiz_category": ("question.manage", "scoped"),
    "api_upload_question_image": ("question.manage", "capability"),
    "api_admin_list_quiz_questions": ("question.manage", "scoped"),
    "api_create_quiz_question": ("question.manage", "scoped"),
    "api_update_quiz_question": ("question.manage", "scoped"),
    "api_batch_update_quiz_questions": ("question.manage", "scoped"),
    "api_import_quiz_questions_url": ("question.manage", "scoped"),
    "api_delete_quiz_question": ("question.manage", "scoped"),
}


def admin_key_override(owner=None) -> bool:
    del owner
    supplied = str(request.headers.get("X-Admin-Key", "") or "")
    key = admin_key()
    return bool(key and supplied and supplied == key)


def require_admin(owner=None):
    """Canonical implementation of the historical teaching-admin guard."""
    if admin_key_override():
        return None
    user = getattr(g, "teacher_user", None)
    if not user:
        return jsonify({
            "error": "請先以管理者帳號登入，或提供正確的 ADMIN_KEY。",
            "loginRequired": True,
        }), 401
    if not (has_permission(user, "user.manage") or has_permission(user, "system.manage")):
        return jsonify({"error": "權限不足：此功能限教學管理者使用。"}), 403
    return None


def legacy_admin_guard(owner, original=None):
    policy = LEGACY_ENDPOINT_POLICIES.get(request.endpoint or "")
    if not policy:
        return require_admin(owner)
    if admin_key_override(owner):
        return None
    permission, mode = policy
    if mode in {"capability", "list"}:
        return scope_filter.denied(owner, permission)[1]
    return scope_filter.scoped_groups(
        owner,
        permission,
        scope_filter.request_groups(owner),
    )[1]


def ensure_07620(base) -> bool:
    """Explicit compatibility hook for the historical account-role maintenance task."""
    del base
    return account_roles.grant_system_admin("07620")


def register_legacy_rbac(base):
    app = base.app

    @app.get("/api/auth/profile")
    def current_profile():
        user = getattr(g, "teacher_user", None)
        if not user:
            return jsonify({"authenticated": False, "user": None})
        row = auth_repository.find_user(user["username"])
        return jsonify({
            "authenticated": bool(row),
            "user": public_user(row, include_roles=True) if row else None,
        })

    base.require_admin = lambda: legacy_admin_guard(base)
    base.require_permission = lambda permission: scope_filter.require_permission(base, permission)
    base.require_any_permission = lambda *permissions: scope_filter.require_any_permission(base, *permissions)
    base.require_system_admin = lambda: scope_filter.denied(base, "system.manage")[1]
    base.require_teacher_workspace = lambda: (
        None
        if (getattr(g, "teacher_user", None) and is_teacher_workspace_user(g.teacher_user))
        else (jsonify({"error": "教師工作區權限不足。"}), 403)
    )
    base.require_scoped_permission = lambda permission, group=None: scope_filter.scoped(
        base, permission, group
    )[1]


__all__ = [
    "LEGACY_ENDPOINT_POLICIES",
    "admin_key_override",
    "ensure_07620",
    "legacy_admin_guard",
    "require_admin",
    "register_legacy_rbac",
]
