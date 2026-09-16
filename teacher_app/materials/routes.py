"""Legacy URL adapter for the canonical material catalog domain."""
from __future__ import annotations

from flask import jsonify, request

from teacher_app.common.errors import ApiError
from teacher_app.materials import bp
from teacher_app.materials import service


ENDPOINTS = (
    "api_list_slides",
    "api_admin_slides",
    "api_update_slide",
    "api_delete_slide",
)


def _legacy_error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra)
    return jsonify(body), exc.status


def _require_login(base):
    if not base._current_user():
        return jsonify({"error": "請先登入後再使用教材。", "loginRequired": True}), 401
    return None


def register_legacy_material_routes(base):
    app = base.app
    if app.extensions.get("teacher_materials_stage51_registered"):
        return app

    def api_list_slides():
        denied = _require_login(base)
        if denied:
            return denied
        return jsonify(service.list_materials(base, request.args.get("area", base.DEFAULT_TRAINING_AREA)))

    def api_admin_slides():
        denied = base.require_admin()
        if denied:
            return denied
        return jsonify(service.list_admin_materials(base))

    def api_update_slide(slide_id):
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.update_material(base, slide_id, request.get_json(silent=True) or {}))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_delete_slide(slide_id):
        denied = base.require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.delete_material(base, slide_id))
        except ApiError as exc:
            return _legacy_error(exc)

    replacements = {
        "api_list_slides": api_list_slides,
        "api_admin_slides": api_admin_slides,
        "api_update_slide": api_update_slide,
        "api_delete_slide": api_delete_slide,
    }
    missing = [name for name in ENDPOINTS if name not in app.view_functions]
    if missing:
        raise RuntimeError(f"material compatibility endpoints missing: {', '.join(missing)}")
    app.view_functions.update(replacements)
    app.extensions["teacher_materials_stage51_registered"] = True
    return app
