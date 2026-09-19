"""Compatibility helpers for material HTTP responses.

The production compatibility host keeps the legacy URL rules and delegates
straight to teacher_app.materials.service.  This module no longer replaces live
Flask view functions at runtime.
"""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.auth import rbac_legacy_adapter
from teacher_app.common import audit, scope
from teacher_app.common.errors import ApiError
from teacher_app.materials import bp
from teacher_app.materials import repository, service
from teacher_app.storage.web_runtime import WebStorageRuntime


def _legacy_error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra)
    return jsonify(body), exc.status


def _login_required(owner=None):
    user = getattr(g, "teacher_user", None)
    if user is None:
        resolver = getattr(owner, "_current_user", None)
        if callable(resolver):
            user = resolver()
    if user:
        return None
    return jsonify({"error": "請先登入後再使用教材。", "loginRequired": True}), 401


def register_material_catalog_routes(owner, *, paths=None, storage_runtime=None):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_material_catalog_routes_registered"):
        return app
    paths = paths or app.config.get("STORAGE_PATHS")
    if paths is None:
        raise RuntimeError("StoragePaths is required for material catalog routes")
    runtime = storage_runtime or WebStorageRuntime(paths)

    def actor():
        user = getattr(g, "teacher_user", None)
        if user is not None:
            return user
        resolver = getattr(owner, "_current_user", None)
        return resolver() if callable(resolver) else None

    def snapshot(item):
        item = item or {}
        return {
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "group": str(item.get("group") or ""),
            "area": str(item.get("area") or ""),
            "category": str(item.get("category") or ""),
            "courseId": str(item.get("courseId") or ""),
            "materialType": str(item.get("materialType") or ""),
            "active": bool(item.get("active", True)),
            "storageBackend": str(item.get("storageBackend") or ""),
        }

    def require_admin():
        if not app.extensions.get("teacher_rbac_681_registered"):
            compat = getattr(owner, "require_admin", None)
            if callable(compat):
                return compat()
        return rbac_legacy_adapter.legacy_admin_guard(app)

    def api_list_slides():
        denied = _login_required(owner)
        if denied:
            return denied
        return jsonify(service.list_materials(request.args.get("area", scope.DEFAULT_TRAINING_AREA)))

    def api_admin_slides():
        denied = require_admin()
        if denied:
            return denied
        return jsonify(service.list_admin_materials())

    def api_update_slide(slide_id):
        denied = require_admin()
        if denied:
            return denied
        before = repository.get_material(slide_id)
        try:
            payload = service.update_material(slide_id, request.get_json(silent=True) or {})
        except ApiError as exc:
            return _legacy_error(exc)
        after = repository.get_material(slide_id)
        if before and after and bool(before.get("active", True)) != bool(after.get("active", True)):
            audit.record_event(
                actor=actor(),
                action="material.publish" if after.get("active", True) else "material.unpublish",
                target_type="material",
                target_id=slide_id,
                group=str(after.get("group") or before.get("group") or ""),
                before=snapshot(before),
                after=snapshot(after),
            )
        return jsonify(payload)

    def api_delete_slide(slide_id):
        denied = require_admin()
        if denied:
            return denied
        before = repository.get_material(slide_id)
        try:
            payload = service.delete_material(slide_id, paths=paths, storage_runtime=runtime)
        except ApiError as exc:
            return _legacy_error(exc)
        audit.record_event(
            actor=actor(),
            action="material.delete",
            target_type="material",
            target_id=slide_id,
            group=str((before or {}).get("group") or ""),
            before=snapshot(before),
        )
        return jsonify(payload)

    app.add_url_rule("/api/slides", endpoint="api_list_slides", view_func=api_list_slides, methods=["GET"])
    app.add_url_rule("/api/slides/admin", endpoint="api_admin_slides", view_func=api_admin_slides, methods=["GET"])
    app.add_url_rule("/api/slides/<slide_id>", endpoint="api_update_slide", view_func=api_update_slide, methods=["PATCH"])
    app.add_url_rule("/api/slides/<slide_id>", endpoint="api_delete_slide", view_func=api_delete_slide, methods=["DELETE"])
    app.extensions["teacher_material_catalog_routes_registered"] = True
    return app


__all__ = ["_legacy_error", "register_material_catalog_routes"]
