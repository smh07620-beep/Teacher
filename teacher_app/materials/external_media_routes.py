"""Canonical Teacher 6.8 external-media HTTP adapter.

External-media validation and persistence live in
``teacher_app.materials.external_media``. This root module preserves the
public URLs, permission gates and legacy JSON response shapes only.
"""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common import scope, scope_filter
from teacher_app.common import audit as audit_store
from teacher_app.common.auth import has_permission, has_role
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


def _hospital_hosts(app):
    configured = app.config.get("EXTERNAL_MEDIA_HOSPITAL_CDN_HOSTS")
    if configured is None:
        configured = app.config.get("DIRECT_MEDIA_ALLOWLIST", [])
    return external_media_service.normalize_hospital_cdn_hosts(configured or ())


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
                _hospital_hosts(app),
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
                _hospital_hosts(app),
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

    @app.get("/api/external-media/report")
    def external_media_report():
        user, denied = scope_filter.denied(owner, "material.manage", "audit.read")
        if denied:
            return denied
        try:
            limit = max(1, min(500, int(request.args.get("limit", "200") or 200)))
        except (TypeError, ValueError):
            limit = 200
        try:
            items = external_media_service.list_external_media_report(
                status=request.args.get("status", ""),
                limit=limit,
            )
        except ApiError as exc:
            return _error(exc)

        # audit.read is organization-wide read-only in the current policy.
        # Group-scoped material managers without audit.read remain confined to
        # their preferred group even though this is a list/report endpoint.
        if not has_permission(user, "audit.read") and any(
            has_role(user, role) for role in ("clinical_teacher", "group_leader")
        ):
            group = scope_filter.preferred_group(user)
            items = [item for item in items if str(item.get("group") or "") == group]
        return jsonify({"items": items, "count": len(items), "readOnly": True})

    @app.post("/api/materials/<material_id>/external-media/verify")
    def verify_external_media(material_id):
        denied = scope_filter.require_permission(owner, "material.manage")
        if denied:
            return denied
        try:
            data = external_media_service.verify_external_media(
                material_id,
                allow_hosts=_hospital_hosts(app),
            )
        except ApiError as exc:
            return _error(exc)
        actor = _current_user(owner) or {}
        audit_store.record_event(
            actor=actor,
            action="external_media.verify",
            target_type="external_media",
            target_id=material_id,
            after={
                "availabilityStatus": data.get("availabilityStatus", ""),
                "lastVerifiedAt": data.get("lastVerifiedAt", ""),
            },
            detail={"provider": data.get("provider", "")},
        )
        return jsonify({"ok": True, "materialId": material_id, "externalMedia": data})

    app.extensions["teacher_external_media_68_registered"] = True
    return app
