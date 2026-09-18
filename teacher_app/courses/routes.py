"""Canonical course and teaching-plan HTTP routes."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.auth import rbac_legacy_adapter
from teacher_app.common import scope
from teacher_app.common.errors import ApiError
from teacher_app.courses import service


def _legacy_error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra)
    return jsonify(body), exc.status


def _login_required():
    if getattr(g, "teacher_user", None):
        return None
    return jsonify({"error": "請先登入後再執行此操作。", "loginRequired": True}), 401


def register_course_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_course_routes_registered"):
        return app

    def require_admin():
        return rbac_legacy_adapter.legacy_admin_guard(app)

    def api_courses():
        denied = _login_required()
        if denied:
            return denied
        area = request.args.get("area", scope.DEFAULT_TRAINING_AREA)
        group = request.args.get("group", "") or None
        return jsonify(service.list_courses(app, area, group, False))

    def api_courses_admin():
        denied = require_admin()
        if denied:
            return denied
        return jsonify(service.list_courses(
            app,
            request.args.get("area", "") or None,
            request.args.get("group", "") or None,
            True,
        ))

    def api_create_course():
        denied = require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.create_course(app, request.get_json(silent=True) or {}))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_update_course(course_id):
        denied = require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.update_course(app, course_id, request.get_json(silent=True) or {}))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_delete_course(course_id):
        denied = require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.delete_course(app, course_id))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_get_teaching_plan(course_id):
        denied = require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.get_teaching_plan(app, course_id))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_save_teaching_plan(course_id):
        denied = require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.save_teaching_plan(app, course_id, request.get_json(silent=True)))
        except ApiError as exc:
            return _legacy_error(exc)

    rules = (
        ("/api/courses", "api_courses", api_courses, ["GET"]),
        ("/api/courses/admin", "api_courses_admin", api_courses_admin, ["GET"]),
        ("/api/courses", "api_create_course", api_create_course, ["POST"]),
        ("/api/courses/<course_id>", "api_update_course", api_update_course, ["PATCH"]),
        ("/api/courses/<course_id>", "api_delete_course", api_delete_course, ["DELETE"]),
        ("/api/courses/<course_id>/plan", "api_get_teaching_plan", api_get_teaching_plan, ["GET"]),
        ("/api/courses/<course_id>/plan", "api_save_teaching_plan", api_save_teaching_plan, ["PUT"]),
    )
    for rule, endpoint, view, methods in rules:
        app.add_url_rule(rule, endpoint=endpoint, view_func=view, methods=methods)

    app.extensions["teacher_course_routes_registered"] = True
    return app


__all__ = ["_legacy_error", "register_course_routes"]
