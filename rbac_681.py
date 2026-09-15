"""Teacher 6.8.1 capability and workspace consolidation.

Normal requests authenticate with the session and are authorized by canonical
roles, capabilities, and a conservative group scope. ``ADMIN_KEY`` remains
only as an emergency compatibility path; ordinary teacher/group-leader work
never depends on it.
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
GROUP_SCOPED_ROLES = {"clinical_teacher", "group_leader"}
GROUP_SCOPED_PERMISSIONS = {
    "material.manage",
    "course.manage",
    "course.edit",
    "question.manage",
    "question.review",
    "exam.manage",
    "exam.publish",
    "result.group.read",
    "group.content.manage",
    "group.result.read",
}

# Legacy endpoints predate capability RBAC and still call require_admin().
# This allow-list translates only teaching/content operations to capabilities;
# user, role, storage, backup, secrets and system settings keep the old strict
# administrator guard.
LEGACY_ENDPOINT_POLICIES = {
    # Materials and background upload flow.
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
    # Courses.
    "api_courses_admin": ("course.manage", "list"),
    "api_create_course": ("course.manage", "scoped"),
    "api_update_course": ("course.manage", "scoped"),
    "api_delete_course": ("course.manage", "scoped"),
    "api_get_teaching_plan": ("course.manage", "scoped"),
    "api_save_teaching_plan": ("course.manage", "scoped"),
    # Legacy question/exam editor.
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

# These creation endpoints use DEFAULT_GROUP when the caller omits group.
DEFAULT_GROUP_ENDPOINTS = {
    "api_enqueue_material_job",
    "api_upload_slide",
    "material_upload_init",
    "api_create_course",
    "api_create_quiz_category",
}

# List endpoints are capability-gated first and then filtered server-side for
# clinical_teacher/group_leader. Cross-group roles receive the full response.
FILTERED_LIST_ENDPOINTS = {
    "api_admin_slides",
    "api_list_material_jobs",
    "api_courses_admin",
    "api_admin_list_quiz_categories",
    "list_bank",
    "learning_analytics",
}


def _denied(base, *permissions):
    user = base._current_user()
    if not user:
        return None, (jsonify({"error": "請先登入。", "loginRequired": True}), 401)
    if not any(has_permission(user, permission) for permission in permissions):
        return None, (jsonify({"error": "權限不足。"}), 403)
    return user, None


def _preferred_group(user):
    return str((user or {}).get("preferredGroup") or (user or {}).get("preferred_group") or "").strip()


def _row_group(value):
    if not isinstance(value, dict):
        return ""
    return str(value.get("group") or value.get("groupKey") or value.get("group_key") or "").strip()


def _json_object(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _category_group(base, category_id):
    category_id = str(category_id or "").strip()
    if not category_id:
        return ""
    try:
        return _row_group(base.get_quiz_category(category_id) or {})
    except Exception:
        return ""


def _question_group(base, question_id):
    question_id = str(question_id or "").strip()
    if not question_id:
        return ""
    try:
        question = base.get_quiz_question(question_id) or {}
    except Exception:
        question = {}
    category_id = str(question.get("quizCategoryId") or question.get("quiz_category_id") or "").strip()
    if category_id:
        return _category_group(base, category_id)
    # Question Bank 2.0 and legacy rows share quiz_questions, but keep a direct
    # DB fallback so authorization does not depend on the presentation helper.
    conn = None
    try:
        conn, kind = base._db_conn()
        ph = "%s" if kind == "postgres" else "?"
        row = conn.execute(f"SELECT quiz_category_id FROM quiz_questions WHERE id={ph}", (question_id,)).fetchone()
        if row:
            category_id = str(dict(row).get("quiz_category_id") or "")
            return _category_group(base, category_id)
    except Exception:
        return ""
    finally:
        if conn is not None:
            conn.close()
    return ""


def _upload_session_group(base, upload_id):
    upload_id = str(upload_id or "").strip()
    if not upload_id:
        return ""
    conn = None
    try:
        conn, kind = base._db_conn()
        ph = "%s" if kind == "postgres" else "?"
        row = conn.execute(f"SELECT payload FROM material_upload_sessions WHERE id={ph}", (upload_id,)).fetchone()
        payload = _json_object(dict(row).get("payload") if row else None)
        return _row_group(payload)
    except Exception:
        return ""
    finally:
        if conn is not None:
            conn.close()


def _blueprint_group(base, blueprint_id):
    blueprint_id = str(blueprint_id or "").strip()
    if not blueprint_id:
        return ""
    conn = None
    try:
        conn, kind = base._db_conn()
        ph = "%s" if kind == "postgres" else "?"
        row = conn.execute(f"SELECT quiz_category_id FROM exam_blueprints WHERE id={ph}", (blueprint_id,)).fetchone()
        return _category_group(base, dict(row).get("quiz_category_id") if row else "")
    except Exception:
        return ""
    finally:
        if conn is not None:
            conn.close()


def _request_groups(base):
    """Resolve every group touched by the current request, conservatively."""
    groups = set()
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    view = request.view_args or {}

    def add(value):
        value = str(value or "").strip()
        if value:
            groups.add(value)

    # Explicit request scope.
    add(body.get("group"))
    add(request.form.get("group"))
    add(request.args.get("group"))
    add(view.get("group_key"))

    # Category scope used by both legacy and Question Bank 2.0 APIs.
    category_ids = {
        str(body.get("quizCategoryId") or "").strip(),
        str(body.get("category") or "").strip(),
        str(request.args.get("quizCategoryId") or "").strip(),
        str(request.args.get("category") or "").strip(),
        str(view.get("category_id") or "").strip(),
    }
    for category_id in category_ids:
        if category_id:
            add(_category_group(base, category_id))

    # Existing resources.
    material_id = view.get("material_id") or view.get("slide_id")
    if material_id:
        try:
            add(_row_group(base.get_material(material_id) or {}))
        except Exception:
            pass

    course_id = view.get("course_id") or body.get("courseId") or request.args.get("courseId")
    if course_id:
        try:
            add(_row_group(base.get_course(course_id) or {}))
        except Exception:
            pass

    question_id = view.get("question_id")
    if question_id:
        add(_question_group(base, question_id))

    blueprint_id = view.get("blueprint_id")
    if blueprint_id:
        add(_blueprint_group(base, blueprint_id))

    job_id = view.get("job_id")
    if job_id:
        try:
            job = base.get_material_job(job_id, include_payload=True) or {}
            add(_row_group(job))
            add(_row_group(_json_object(job.get("payload"))))
        except Exception:
            pass

    upload_id = view.get("upload_id")
    if upload_id:
        add(_upload_session_group(base, upload_id))

    # Batch question updates may touch multiple question/category scopes.
    items = body.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            add(_category_group(base, item.get("quizCategoryId") or item.get("category")))
            add(_question_group(base, item.get("id") or item.get("questionId")))

    if not groups and (request.endpoint or "") in DEFAULT_GROUP_ENDPOINTS:
        add(getattr(base, "DEFAULT_GROUP", ""))
    return {group for group in groups if group}


def _scoped_groups(base, permission, groups, *, allow_unscoped=False):
    user, denied = _denied(base, permission)
    if denied:
        return None, denied
    if is_system_admin(user) or has_role(user, "education_admin"):
        return user, None
    if any(has_role(user, role) for role in GROUP_SCOPED_ROLES):
        own = _preferred_group(user)
        groups = {str(group or "").strip() for group in (groups or set()) if str(group or "").strip()}
        if groups and own and groups == {own}:
            return user, None
        if allow_unscoped and not groups:
            return user, None
        return None, (jsonify({"error": "此資源不在你的授權範圍。"}), 403)
    return None, (jsonify({"error": "權限不足。"}), 403)


def _scoped(base, permission, group=None):
    groups = {str(group).strip()} if group is not None and str(group).strip() else _request_groups(base)
    return _scoped_groups(base, permission, groups)


def _admin_key_override(base):
    supplied = str(request.headers.get("X-Admin-Key", "") or "")
    key = str(getattr(base, "ADMIN_KEY", "") or "")
    return bool(key and supplied and supplied == key)


def _legacy_admin_guard(base, original):
    policy = LEGACY_ENDPOINT_POLICIES.get(request.endpoint or "")
    if not policy:
        return original()
    if _admin_key_override(base):
        return None
    permission, mode = policy
    if mode in {"capability", "list"}:
        return _denied(base, permission)[1]
    return _scoped_groups(base, permission, _request_groups(base))[1]


def _require_permission(base, permission):
    # When a scoped resource is identifiable, capability checks also enforce
    # its group. This protects newer adapters such as external-media updates.
    if permission in GROUP_SCOPED_PERMISSIONS:
        groups = _request_groups(base)
        if groups:
            return _scoped_groups(base, permission, groups)[1]
    return _denied(base, permission)[1]


def _require_any_permission(base, *permissions):
    user, denied = _denied(base, *permissions)
    if denied:
        return denied
    if not any(has_role(user, role) for role in GROUP_SCOPED_ROLES):
        return None
    # Read-only auditor does not enter this branch. Scoped teachers may list
    # their bank/analytics and the response is filtered below.
    if (request.endpoint or "") in FILTERED_LIST_ENDPOINTS:
        return None
    scoped = [p for p in permissions if p in GROUP_SCOPED_PERMISSIONS and has_permission(user, p)]
    if scoped:
        return _scoped_groups(base, scoped[0], _request_groups(base))[1]
    return None


def _item_group(base, item):
    if not isinstance(item, dict):
        return ""
    group = _row_group(item)
    if group:
        return group
    payload = _json_object(item.get("payload"))
    group = _row_group(payload)
    if group:
        return group
    category_id = item.get("quizCategoryId") or item.get("quiz_category_id") or item.get("categoryId")
    if category_id:
        group = _category_group(base, category_id)
        if group:
            return group
    material_id = item.get("materialId") or item.get("material_id") or item.get("id") if (request.endpoint or "") in {"api_admin_slides", "learning_analytics"} else item.get("materialId") or item.get("material_id")
    if material_id:
        try:
            group = _row_group(base.get_material(material_id) or {})
            if group:
                return group
        except Exception:
            pass
    course_id = item.get("courseId") or item.get("course_id")
    if course_id:
        try:
            return _row_group(base.get_course(course_id) or {})
        except Exception:
            pass
    return ""


def _filter_items(base, items, group):
    return [item for item in items if _item_group(base, item) == group]


def _filter_scoped_response(base, response):
    endpoint = request.endpoint or ""
    if endpoint not in FILTERED_LIST_ENDPOINTS or response.status_code >= 400 or not response.is_json:
        return response
    user = base._current_user()
    if not user or not any(has_role(user, role) for role in GROUP_SCOPED_ROLES):
        return response
    group = _preferred_group(user)
    if not group:
        response.set_data(json.dumps([] if endpoint != "list_bank" else {"items": []}, ensure_ascii=False))
        response.mimetype = "application/json"
        return response
    payload = response.get_json(silent=True)
    changed = False
    if isinstance(payload, list):
        payload = _filter_items(base, payload, group)
        changed = True
    elif isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            payload["items"] = _filter_items(base, payload["items"], group)
            changed = True
        if isinstance(payload.get("jobs"), list):
            payload["jobs"] = _filter_items(base, payload["jobs"], group)
            changed = True
    if changed:
        response.set_data(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        response.mimetype = "application/json"
    return response


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

    # Public helpers are response-shaped for legacy routes. Replace the old
    # require_admin only with the explicit endpoint adapter above; all other
    # administrative routes retain their historical system/user-management
    # requirement.
    original_require_admin = base.require_admin
    base.require_admin = lambda: _legacy_admin_guard(base, original_require_admin)
    base.require_permission = lambda permission: _require_permission(base, permission)
    base.require_any_permission = lambda *permissions: _require_any_permission(base, *permissions)
    base.require_system_admin = lambda: _denied(base, "system.manage")[1]
    base.require_teacher_workspace = lambda: (
        None if (base._current_user() and is_teacher_workspace_user(base._current_user()))
        else (jsonify({"error": "教師工作區權限不足。"}), 403)
    )
    base.require_scoped_permission = lambda permission, group=None: _scoped(base, permission, group)[1]

    @app.after_request
    def teacher_scope_filter(response):
        return _filter_scoped_response(base, response)

    # ``/system`` is the learner shell. Its management mode is a distinct
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
        if extension in OFFICE_EXTENSIONS:
            denied = _scoped_groups(base, "material.manage", {_row_group(entry)})[1]
            if denied:
                return denied
        return app.extensions["teacher_legacy_view_material"](material_id)

    for rule in app.url_map.iter_rules():
        if rule.rule == "/view/<material_id>" and "GET" in rule.methods:
            app.extensions["teacher_legacy_view_material"] = app.view_functions[rule.endpoint]
            app.view_functions[rule.endpoint] = learner_office_view

    app.extensions["teacher_rbac_681_registered"] = True
    return app
