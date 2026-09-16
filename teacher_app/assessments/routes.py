"""Legacy URL adapter for canonical assessment configuration."""
from __future__ import annotations

from flask import jsonify, request

from teacher_app.assessments import service
from teacher_app.common.errors import ApiError


ENDPOINTS = (
    "api_list_quiz_categories",
    "api_admin_list_quiz_categories",
    "api_create_quiz_category",
    "api_update_quiz_category",
    "api_review_quiz_category",
    "api_quiz_publications",
    "api_publish_quiz_category",
    "api_quiz_category_materials",
    "api_update_quiz_category_materials",
    "api_delete_quiz_category",
)


def _legacy_error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra)
    return jsonify(body), exc.status


def _require_login(base):
    if not base._current_user():
        return jsonify({"error": "請先登入後再使用教材。", "loginRequired": True}), 401
    return None


def register_legacy_assessment_routes(base):
    app = base.app
    if app.extensions.get("teacher_assessments_stage51_registered"):
        return app

    def api_list_quiz_categories():
        denied = _require_login(base)
        if denied:
            return denied
        return jsonify(
            service.list_categories(
                base,
                request.args.get("group", "") or None,
                request.args.get("area", base.DEFAULT_TRAINING_AREA),
                False,
            )
        )

    def api_admin_list_quiz_categories():
        denied = base.require_admin()
        if denied:
            return denied
        return jsonify(
            service.list_categories(
                base,
                request.args.get("group", "") or None,
                request.args.get("area", base.DEFAULT_TRAINING_AREA),
                True,
            )
        )

    def api_create_quiz_category():
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.create_category(base, request.get_json(silent=True) or {}))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_update_quiz_category(category_id):
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.update_category(base, category_id, request.get_json(silent=True) or {}))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_review_quiz_category(category_id):
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.review_category(base, category_id, request.get_json(silent=True) or {}))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_quiz_publications(category_id):
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.list_publications(base, category_id))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_publish_quiz_category(category_id):
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.publish_category(base, category_id))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_quiz_category_materials(category_id):
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.category_materials(base, category_id))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_update_quiz_category_materials(category_id):
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.update_category_materials(base, category_id, request.get_json(silent=True) or {}))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_delete_quiz_category(category_id):
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.delete_category(base, category_id))
        except ApiError as exc:
            return _legacy_error(exc)

    replacements = {
        "api_list_quiz_categories": api_list_quiz_categories,
        "api_admin_list_quiz_categories": api_admin_list_quiz_categories,
        "api_create_quiz_category": api_create_quiz_category,
        "api_update_quiz_category": api_update_quiz_category,
        "api_review_quiz_category": api_review_quiz_category,
        "api_quiz_publications": api_quiz_publications,
        "api_publish_quiz_category": api_publish_quiz_category,
        "api_quiz_category_materials": api_quiz_category_materials,
        "api_update_quiz_category_materials": api_update_quiz_category_materials,
        "api_delete_quiz_category": api_delete_quiz_category,
    }
    missing = [name for name in ENDPOINTS if name not in app.view_functions]
    if missing:
        raise RuntimeError(f"assessment compatibility endpoints missing: {', '.join(missing)}")
    app.view_functions.update(replacements)
    app.extensions["teacher_assessments_stage51_registered"] = True
    return app
