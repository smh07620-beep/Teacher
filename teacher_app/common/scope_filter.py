"""Server-side group scope resolution and response filtering for legacy APIs."""
from __future__ import annotations

import json

from flask import g, jsonify, request

from teacher_app.assessments import repository as assessment_repository
from teacher_app.common.auth import has_permission, has_role, is_system_admin
from teacher_app.common import scope
from teacher_app.courses import repository as course_repository
from teacher_app.materials import repository as material_repository
from teacher_app.worker import repository as worker_repository


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

DEFAULT_GROUP_ENDPOINTS = {
    "api_enqueue_material_job",
    "api_upload_slide",
    "material_upload_init",
    "api_create_course",
    "api_create_quiz_category",
}

FILTERED_LIST_ENDPOINTS = {
    "api_admin_slides",
    "api_list_material_jobs",
    "api_courses_admin",
    "api_admin_list_quiz_categories",
    "list_bank",
    "learning_analytics",
}

# These routes load the upload session through their injected Worker runtime and
# immediately call ``upload_session_guard(session)``.  Re-querying the global
# repository in the generic RBAC pre-guard can target a different isolated test
# database and, more importantly, would duplicate canonical ownership.  Defer
# resource scope to the route's already fail-closed session guard.
UPLOAD_SESSION_SCOPE_OWNER_ENDPOINTS = {
    "material_upload_status",
    "material_upload_resume",
    "material_upload_complete",
    "material_upload_abort",
}

_SCOPE_FAILURE_ATTR = "teacher_scope_resolution_failed"
_SCOPE_FAILURE_MESSAGE = "無法確認資源授權範圍，請稍後再試。"
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_SCOPE_GROUP_KEYS = ("group", "groupKey", "preferredGroup")
_SCOPE_AREA_KEYS = ("area", "trainingArea", "preferredArea")


def _current_user(owner=None):
    """Return the request-bound canonical actor, with a test-only fallback.

    Production composition binds ``g.teacher_user`` before these guards run.
    The fallback keeps isolated compatibility unit tests usable while callers
    converge away from base-shaped fixtures.
    """
    user = getattr(g, "teacher_user", None)
    if user is not None:
        return user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _app(owner):
    return getattr(owner, "app", owner)


def denied(owner, *permissions):
    user = _current_user(owner)
    if not user:
        return None, (jsonify({"error": "請先登入。", "loginRequired": True}), 401)
    if not any(has_permission(user, permission) for permission in permissions):
        return None, (jsonify({"error": "權限不足。"}), 403)
    return user, None


def preferred_group(user) -> str:
    return str(
        (user or {}).get("preferredGroup")
        or (user or {}).get("preferred_group")
        or ""
    ).strip()


def row_group(value) -> str:
    if not isinstance(value, dict):
        return ""
    return str(
        value.get("group")
        or value.get("groupKey")
        or value.get("group_key")
        or ""
    ).strip()


def json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _mark_scope_resolution_failed() -> None:
    setattr(g, _SCOPE_FAILURE_ATTR, True)


def scope_resolution_failed() -> bool:
    return bool(getattr(g, _SCOPE_FAILURE_ATTR, False))


def _scope_resolution_denied(owner, *permissions):
    if not scope_resolution_failed():
        return None
    user, denied_response = denied(owner, *permissions)
    if denied_response:
        return denied_response
    if not any(has_role(user, role) for role in GROUP_SCOPED_ROLES):
        return None
    return jsonify({"error": _SCOPE_FAILURE_MESSAGE, "scopeResolutionFailed": True}), 503


def _explicit_scope_values(mapping, keys):
    if mapping is None:
        return []
    values = []
    for key in keys:
        try:
            present = key in mapping
        except TypeError:
            present = False
        if present:
            values.append((key, mapping.get(key)))
    return values


def validate_request_scope_values(owner=None):
    """Reject malformed explicit scope on authenticated write requests.

    Historical read-side normalization intentionally keeps default fallback for
    legacy rows. Browser/API writes are different: an explicit unknown group or
    training area must never silently become grpBio/internal. This guard covers
    canonical and retained compatibility routes before their service layer runs.
    Worker-token routes do not have a session actor and validate captured scope
    again at their canonical commit boundary.
    """
    if request.method not in _MUTATING_METHODS:
        return None
    if not _current_user(owner):
        return None

    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    sources = (body, request.form, request.args)
    try:
        for source in sources:
            for _key, value in _explicit_scope_values(source, _SCOPE_GROUP_KEYS):
                scope.validate_group(value, default=None)
            for _key, value in _explicit_scope_values(source, _SCOPE_AREA_KEYS):
                scope.validate_area(value, default=None)
    except ValueError as exc:
        return jsonify({"error": str(exc), "invalidScope": True}), 400
    return None


def category_group(owner, category_id) -> str:
    del owner
    category_id = str(category_id or "").strip()
    if not category_id:
        return ""
    try:
        return row_group(assessment_repository.get_category(category_id) or {})
    except Exception:
        return ""


def question_group(owner, question_id) -> str:
    question_id = str(question_id or "").strip()
    if not question_id:
        return ""
    try:
        question = assessment_repository.get_question(question_id) or {}
    except Exception:
        question = {}
    category_id = str(
        question.get("quizCategoryId") or question.get("quiz_category_id") or ""
    ).strip()
    return category_group(owner, category_id) if category_id else ""


def upload_session_group(owner, upload_id) -> str:
    upload_id = str(upload_id or "").strip()
    if not upload_id:
        return ""
    try:
        session = worker_repository.get_upload_session(upload_id) or {}
        return row_group(json_object(session.get("payload")))
    except Exception:
        return ""


def blueprint_group(owner, blueprint_id) -> str:
    blueprint_id = str(blueprint_id or "").strip()
    if not blueprint_id:
        return ""
    try:
        blueprint = assessment_repository.get_blueprint(blueprint_id) or {}
    except Exception:
        return ""
    return category_group(owner, blueprint.get("quiz_category_id"))


def request_groups(owner=None) -> set[str]:
    """Resolve every group touched by the current request, conservatively.

    Explicit resource-id lookups are fail-closed for group-scoped actors. When
    an existing target id cannot be resolved to a group, ``require_permission``
    returns a generic 503 instead of silently degrading to capability-only
    authorization. Organization/system-wide actors keep their existing scope.

    Legacy ``category`` query/form values are not necessarily category ids, so
    only explicit ``quizCategoryId`` / route ids are treated as strict resource
    lookups. Upload-session routes defer to their canonical session guard.
    """
    groups: set[str] = set()
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    view = request.view_args or {}

    def add(value):
        value = str(value or "").strip()
        if value:
            groups.add(value)

    def add_required(value):
        value = str(value or "").strip()
        if value:
            groups.add(value)
        else:
            _mark_scope_resolution_failed()

    add(body.get("group"))
    add(request.form.get("group"))
    add(request.args.get("group"))
    add(view.get("group_key"))

    strict_category_ids = {
        str(body.get("quizCategoryId") or "").strip(),
        str(request.args.get("quizCategoryId") or "").strip(),
        str(view.get("category_id") or "").strip(),
    }
    for category_id in strict_category_ids:
        if category_id:
            add_required(category_group(owner, category_id))

    # Historical ``category`` can also be a display/filter label. Resolve it
    # opportunistically but do not turn a non-id label into a scope outage.
    for category_value in (
        body.get("category"),
        request.args.get("category"),
    ):
        if category_value:
            add(category_group(owner, category_value))

    material_id = view.get("material_id") or view.get("slide_id")
    if material_id:
        try:
            add_required(row_group(material_repository.get_material(material_id) or {}))
        except Exception:
            _mark_scope_resolution_failed()

    course_id = view.get("course_id") or body.get("courseId") or request.args.get("courseId")
    if course_id:
        try:
            add_required(row_group(course_repository.get_course(course_id) or {}))
        except Exception:
            _mark_scope_resolution_failed()

    question_id = view.get("question_id")
    if question_id:
        add_required(question_group(owner, question_id))

    blueprint_id = view.get("blueprint_id")
    if blueprint_id:
        add_required(blueprint_group(owner, blueprint_id))

    job_id = view.get("job_id")
    if job_id:
        try:
            job = worker_repository.get_material_job(
                str(job_id),
                include_payload=True,
            ) or {}
            job_group = row_group(job) or row_group(json_object(job.get("payload")))
            add_required(job_group)
        except Exception:
            _mark_scope_resolution_failed()

    upload_id = view.get("upload_id")
    if upload_id and (request.endpoint or "") not in UPLOAD_SESSION_SCOPE_OWNER_ENDPOINTS:
        add_required(upload_session_group(owner, upload_id))

    items = body.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            explicit_category_id = item.get("quizCategoryId") or item.get("categoryId")
            if explicit_category_id:
                add_required(category_group(owner, explicit_category_id))
            elif item.get("category"):
                add(category_group(owner, item.get("category")))
            item_question_id = item.get("id") or item.get("questionId")
            if item_question_id:
                add_required(question_group(owner, item_question_id))

    ids = body.get("ids")
    if isinstance(ids, list):
        for item_question_id in ids:
            if item_question_id:
                add_required(question_group(owner, item_question_id))

    if not groups and not scope_resolution_failed() and (request.endpoint or "") in DEFAULT_GROUP_ENDPOINTS:
        add(scope.DEFAULT_GROUP)
    return {group for group in groups if group}


def scoped_groups(owner, permission, groups, *, allow_unscoped=False):
    user, denied_response = denied(owner, permission)
    if denied_response:
        return None, denied_response
    if is_system_admin(user) or has_role(user, "education_admin"):
        return user, None
    if any(has_role(user, role) for role in GROUP_SCOPED_ROLES):
        own = preferred_group(user)
        groups = {
            str(group or "").strip()
            for group in (groups or set())
            if str(group or "").strip()
        }
        if groups and own and groups == {own}:
            return user, None
        if allow_unscoped and not groups:
            return user, None
        return None, (jsonify({"error": "此資源不在你的授權範圍。"}), 403)
    return None, (jsonify({"error": "權限不足。"}), 403)


def scoped(owner, permission, group=None):
    groups = (
        {str(group).strip()}
        if group is not None and str(group).strip()
        else request_groups(owner)
    )
    resolution_denied = _scope_resolution_denied(owner, permission)
    if resolution_denied:
        return None, resolution_denied
    return scoped_groups(owner, permission, groups)


def require_permission(owner, permission):
    if permission in GROUP_SCOPED_PERMISSIONS:
        groups = request_groups(owner)
        resolution_denied = _scope_resolution_denied(owner, permission)
        if resolution_denied:
            return resolution_denied
        if groups:
            return scoped_groups(owner, permission, groups)[1]
    return denied(owner, permission)[1]


def require_any_permission(owner, *permissions):
    user, denied_response = denied(owner, *permissions)
    if denied_response:
        return denied_response
    if not any(has_role(user, role) for role in GROUP_SCOPED_ROLES):
        return None
    if (request.endpoint or "") in FILTERED_LIST_ENDPOINTS:
        return None
    scoped_permissions = [
        permission
        for permission in permissions
        if permission in GROUP_SCOPED_PERMISSIONS and has_permission(user, permission)
    ]
    if scoped_permissions:
        groups = request_groups(owner)
        resolution_denied = _scope_resolution_denied(owner, *scoped_permissions)
        if resolution_denied:
            return resolution_denied
        return scoped_groups(owner, scoped_permissions[0], groups)[1]
    return None


def item_group(owner, item) -> str:
    if not isinstance(item, dict):
        return ""
    group = row_group(item)
    if group:
        return group
    payload = json_object(item.get("payload"))
    group = row_group(payload)
    if group:
        return group
    category_id = (
        item.get("quizCategoryId")
        or item.get("quiz_category_id")
        or item.get("categoryId")
    )
    if category_id:
        group = category_group(owner, category_id)
        if group:
            return group
    material_id = item.get("materialId") or item.get("material_id")
    if not material_id and (request.endpoint or "") in {"api_admin_slides", "learning_analytics"}:
        material_id = item.get("id")
    if material_id:
        try:
            group = row_group(material_repository.get_material(material_id) or {})
            if group:
                return group
        except Exception:
            pass
    course_id = item.get("courseId") or item.get("course_id")
    if course_id:
        try:
            return row_group(course_repository.get_course(course_id) or {})
        except Exception:
            pass
    return ""


def filter_items(owner, items, group):
    return [item for item in items if item_group(owner, item) == group]


def filter_scoped_response(owner, response):
    endpoint = request.endpoint or ""
    if (
        endpoint not in FILTERED_LIST_ENDPOINTS
        or response.status_code >= 400
        or not response.is_json
    ):
        return response
    user = _current_user(owner)
    if not user or not any(has_role(user, role) for role in GROUP_SCOPED_ROLES):
        return response
    group = preferred_group(user)
    if not group:
        response.set_data(
            json.dumps([] if endpoint != "list_bank" else {"items": []}, ensure_ascii=False)
        )
        response.mimetype = "application/json"
        return response
    payload = response.get_json(silent=True)
    changed = False
    if isinstance(payload, list):
        payload = filter_items(owner, payload, group)
        changed = True
    elif isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            payload["items"] = filter_items(owner, payload["items"], group)
            changed = True
        if isinstance(payload.get("jobs"), list):
            payload["jobs"] = filter_items(owner, payload["jobs"], group)
            changed = True
    if changed:
        response.set_data(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        response.mimetype = "application/json"
    return response


def register_scope_filter(owner):
    app = _app(owner)

    @app.before_request
    def teacher_scope_write_validation():
        return validate_request_scope_values(owner)

    @app.after_request
    def teacher_scope_filter(response):
        return filter_scoped_response(owner, response)


__all__ = [
    "DEFAULT_GROUP_ENDPOINTS",
    "FILTERED_LIST_ENDPOINTS",
    "GROUP_SCOPED_PERMISSIONS",
    "GROUP_SCOPED_ROLES",
    "UPLOAD_SESSION_SCOPE_OWNER_ENDPOINTS",
    "category_group",
    "denied",
    "filter_scoped_response",
    "preferred_group",
    "question_group",
    "register_scope_filter",
    "request_groups",
    "require_any_permission",
    "require_permission",
    "row_group",
    "scope_resolution_failed",
    "scoped",
    "scoped_groups",
    "validate_request_scope_values",
]
