"""Legacy URL adapter for the canonical course domain."""
from __future__ import annotations

from flask import jsonify, request

from teacher_app.common.errors import ApiError
from teacher_app.courses import service


ENDPOINTS = (
    "api_courses",
    "api_courses_admin",
    "api_create_course",
    "api_update_course",
    "api_delete_course",
    "api_get_teaching_plan",
    "api_save_teaching_plan",
)


def _legacy_error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra)
    return jsonify(body), exc.status


def _require_login(base):
    if not base._current_user():
        return jsonify({"error": "請先登入後再使用教材。", "loginRequired": True}), 401
    return None


def register_legacy_course_routes(base):
    app = base.app
    if app.extensions.get("teacher_courses_stage51_registered"):
        return app

    def api_courses():
        denied = _require_login(base)
        if denied:
            return denied
        try:
            area = request.args.get("area", base.DEFAULT_TRAINING_AREA)
            group = request.args.get("group", "") or None
            return jsonify(service.list_courses(base, area, group, False))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_courses_admin():
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(
                service.list_courses(
                    base,
                    request.args.get("area", "") or None,
                    request.args.get("group", "") or None,
                    True,
                )
            )
        except ApiError as exc:
            return _legacy_error(exc)

    def api_create_course():
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.create_course(base, request.get_json(silent=True) or {}))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_update_course(course_id):
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.update_course(base, course_id, request.get_json(silent=True) or {}))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_delete_course(course_id):
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.delete_course(base, course_id))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_get_teaching_plan(course_id):
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.get_teaching_plan(base, course_id))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_save_teaching_plan(course_id):
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.save_teaching_plan(base, course_id, request.get_json(silent=True)))
        except ApiError as exc:
            return _legacy_error(exc)

    replacements = {
        "api_courses": api_courses,
        "api_courses_admin": api_courses_admin,
        "api_create_course": api_create_course,
        "api_update_course": api_update_course,
        "api_delete_course": api_delete_course,
        "api_get_teaching_plan": api_get_teaching_plan,
        "api_save_teaching_plan": api_save_teaching_plan,
    }
    missing = [name for name in ENDPOINTS if name not in app.view_functions]
    if missing:
        raise RuntimeError(f"course compatibility endpoints missing: {', '.join(missing)}")
    app.view_functions.update(replacements)
    app.extensions["teacher_courses_stage51_registered"] = True
    return app
