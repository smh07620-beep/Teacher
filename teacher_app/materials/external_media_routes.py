"""Canonical Teacher 6.8 external-media HTTP adapter.

External-media validation and persistence live in
``teacher_app.materials.external_media``. This root module preserves the
public URLs, permission gates and legacy JSON response shapes only.
"""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common import scope, scope_filter
from teacher_app.common.errors import ApiError
from teacher_app.materials import external_media as external_media_service


# Compatibility exports retained for acceptance tests and older imports.
DIRECT_HOSTS = external_media_service.DIRECT_HOSTS
VIDEO_TYPES = external_media_service.VIDEO_TYPES
now = external_media_service.now
validate_external_url = external_media_service.validate_external_url


def _error(exc: ApiError):
    return jsonify({"error": exc.message}), exc.status


def _app(owner):
    return getattr(owner, "app", owner)


def _current_user(owner=None):
    if hasattr(g, "teacher_user"):
        return g.teacher_user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def register_external_media(owner):
    app = _app(owner)
    if app.extensions.get("teacher_external_media_68_registered"):
        return app

    @app.put("/api/materials/<material_id>/external-media")
    def put_external_media(material_id):
        denied = scope_filter.require_permission(owner, "material.manage")
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            data = external_media_service.set_external_media(
                material_id,
                body.get("url"),
                app.config.get("DIRECT_MEDIA_ALLOWLIST", []),
            )
        except ApiError as exc:
            return _error(exc)
        return jsonify({"ok": True, "materialId": material_id, **data})

    @app.post("/api/materials/external")
    def create_external_material():
        """Create an external video record without fetching or storing it."""
        body = request.get_json(silent=True) or {}
        denied = scope_filter.scoped(
            owner,
            "material.manage",
            str(body.get("group") or scope.DEFAULT_GROUP),
        )[1]
        if denied:
            return denied
        try:
            result = external_media_service.create_external_material(
                body,
                app.config.get("DIRECT_MEDIA_ALLOWLIST", []),
            )
        except ApiError as exc:
            return _error(exc)
        return jsonify({"ok": True, **result}), 201

    @app.get("/api/materials/<material_id>/external-media")
    def get_external_media(material_id):
        if not _current_user(owner):
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        data = external_media_service.get_external_media(material_id)
        return jsonify({"externalMedia": data})

    app.extensions["teacher_external_media_68_registered"] = True
    return app
