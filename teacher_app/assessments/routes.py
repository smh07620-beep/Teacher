"""Canonical assessment-category HTTP routes."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.assessments import service
from teacher_app.auth import rbac_legacy_adapter
from teacher_app.common import scope
from teacher_app.common.errors import ApiError


def _legacy_error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra)
    return jsonify(body), exc.status


def _login_required():
    if getattr(g, "teacher_user", None):
        return None
    return jsonify({"error": "請先登入後再執行此操作。", "loginRequired": True}), 401


def register_assessment_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_assessment_routes_registered"):
        return app

    def require_admin():
        return rbac_legacy_adapter.legacy_admin_guard(app)

    def api_list_quiz_categories():
        denied = _login_required()
        if denied:
            return denied
        return jsonify(service.list_categories(
            app,
            request.args.get("group", "") or None,
            request.args.get("area", scope.DEFAULT_TRAINING_AREA),
            False,
        ))

    def api_admin_list_quiz_categories():
        denied = require_admin()
        if denied:
            return denied
        return jsonify(service.list_categories(
            app,
            request.args.get("group", "") or None,
            request.args.get("area", scope.DEFAULT_TRAINING_AREA),
            True,
        ))

    def guarded(handler, *args):
        denied = require_admin()
        if denied:
            return denied
        try:
            return jsonify(handler(*args))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_create_quiz_category():
        return guarded(service.create_category, app, request.get_json(silent=True) or {})

    def api_update_quiz_category(category_id):
        return guarded(service.update_category, app, category_id, request.get_json(silent=True) or {})

    def api_review_quiz_category(category_id):
        return guarded(service.review_category, app, category_id, request.get_json(silent=True) or {})

    def api_quiz_publications(category_id):
        return guarded(service.list_publications, app, category_id)

    def api_publish_quiz_category(category_id):
        return guarded(service.publish_category, app, category_id)

    def api_quiz_category_materials(category_id):
        return guarded(service.category_materials, app, category_id)

    def api_update_quiz_category_materials(category_id):
        return guarded(service.update_category_materials, app, category_id, request.get_json(silent=True) or {})

    def api_delete_quiz_category(category_id):
        return guarded(service.delete_category, app, category_id)

    rules = (
        ("/api/quiz-categories", "api_list_quiz_categories", api_list_quiz_categories, ["GET"]),
        ("/api/quiz-categories/admin", "api_admin_list_quiz_categories", api_admin_list_quiz_categories, ["GET"]),
        ("/api/quiz-categories", "api_create_quiz_category", api_create_quiz_category, ["POST"]),
        ("/api/quiz-categories/<category_id>", "api_update_quiz_category", api_update_quiz_category, ["PATCH"]),
        ("/api/quiz-categories/<category_id>/review", "api_review_quiz_category", api_review_quiz_category, ["POST"]),
        ("/api/quiz-categories/<category_id>/publications", "api_quiz_publications", api_quiz_publications, ["GET"]),
        ("/api/quiz-categories/<category_id>/publish", "api_publish_quiz_category", api_publish_quiz_category, ["POST"]),
        ("/api/quiz-categories/<category_id>/materials", "api_quiz_category_materials", api_quiz_category_materials, ["GET"]),
        ("/api/quiz-categories/<category_id>/materials", "api_update_quiz_category_materials", api_update_quiz_category_materials, ["PUT"]),
        ("/api/quiz-categories/<category_id>", "api_delete_quiz_category", api_delete_quiz_category, ["DELETE"]),
    )
    for rule, endpoint, view, methods in rules:
        app.add_url_rule(rule, endpoint=endpoint, view_func=view, methods=methods)

    app.extensions["teacher_assessment_routes_registered"] = True
    return app


__all__ = ["_legacy_error", "register_assessment_routes"]
