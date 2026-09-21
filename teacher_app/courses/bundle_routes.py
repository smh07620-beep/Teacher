"""Canonical Course Wizard bundle HTTP adapter.

Retry-safe course/exam bundle creation lives in ``teacher_app.courses.bundle``.
This root module preserves the public URL, capability gates and response
projection only. Schema registration lives in ``schema_migrations``.
"""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.maintenance.migrations import _course_bundle_idempotency_72
from teacher_app.assessments import repository as assessment_repository
from teacher_app.common import scope, scope_filter
from teacher_app.common.errors import ApiError
from teacher_app.courses import bundle as bundle_service
from teacher_app.courses import repository as course_repository


MIGRATION_ID = bundle_service.MIGRATION_ID
WORKFLOW_RE = bundle_service.WORKFLOW_RE
EXAM_MODES = bundle_service.EXAM_MODES


def _app(owner):
    return getattr(owner, "app", owner)


def _hydrate(result: dict) -> dict:
    """Preserve the legacy material/course response projection only."""
    output = dict(result or {})
    course = output.get("course") or {}
    category = output.get("quizCategory") or None
    try:
        current = course_repository.get_course(str(course.get("id") or "")) if course else None
        if current:
            output["course"] = current
    except Exception:
        pass
    if category:
        try:
            current = assessment_repository.get_category_full(str(category.get("id") or ""))
            if current:
                output["quizCategory"] = current
        except Exception:
            pass
    return output


def _error(exc: ApiError):
    body = {"error": exc.message}
    if exc.code in {"IDEMPOTENCY_KEY_REUSED", "WORKFLOW_IN_PROGRESS"}:
        body["code"] = exc.code
    if exc.extra.get("loginRequired"):
        body["loginRequired"] = True
    return jsonify(body), exc.status


def register_course_bundle_72(owner):
    app = _app(owner)
    if app.extensions.get("teacher_course_bundle_72_registered"):
        return app

    def create_course_bundle():
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"error": "請提供有效的建立資料。"}), 400
        try:
            scope.validate_group(data.get("group", scope.DEFAULT_GROUP))
            scope.validate_area(data.get("area", scope.DEFAULT_TRAINING_AREA))
        except ValueError as exc:
            return jsonify({"error": str(exc), "invalidScope": True}), 400

        # Capability/RBAC remains at the existing HTTP boundary.
        denied = scope_filter.require_permission(app, "course.manage")
        if denied:
            return denied
        exam_mode = str(data.get("examMode") or "later").strip().lower()
        if exam_mode != "later":
            denied = scope_filter.require_permission(app, "question.manage")
            if denied:
                return denied

        try:
            result, status_code = bundle_service.create_bundle(
                getattr(g, "teacher_user", None),
                data,
            )
        except ApiError as exc:
            return _error(exc)
        except Exception:
            return jsonify({
                "error": "建立課程流程失敗，未完成的資料已回復；可使用相同流程識別碼重試。"
            }), 500

        return jsonify(_hydrate(result)), status_code

    app.add_url_rule(
        "/api/course-bundles",
        endpoint="course_bundle_create_72",
        view_func=create_course_bundle,
        methods=["POST"],
    )
    app.extensions["teacher_course_bundle_72_registered"] = True
    return app
