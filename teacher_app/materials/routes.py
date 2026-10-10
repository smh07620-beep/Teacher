"""Compatibility helpers for material HTTP responses.

The production compatibility host keeps the legacy URL rules and delegates
straight to teacher_app.materials.service.  This module no longer replaces live
Flask view functions at runtime.
"""
from __future__ import annotations

from flask import current_app, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

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
            "currentVersion": int(item.get("currentVersion") or 1),
            "requiredCompletionVersion": int(item.get("requiredCompletionVersion") or 1),
            "versionUpdatedAt": str(item.get("versionUpdatedAt") or ""),
            "versionUpdatedBy": str(item.get("versionUpdatedBy") or ""),
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

    def api_material_purge_readiness(slide_id):
        denied = require_admin()
        if denied:
            return denied
        current_actor = actor() or {}
        roles = set(current_actor.get("roles") or [])
        if str(current_actor.get("role") or ""):
            roles.add(str(current_actor.get("role")))
        if "system_admin" not in roles:
            return jsonify({"error": "只有系統管理員可以檢查教材永久清除條件。"}), 403
        payload = service.material_purge_readiness(slide_id)
        if payload.get("purgeAllowed") and payload.get("materialExists"):
            serializer = URLSafeTimedSerializer(str(current_app.secret_key), salt="material-purge-v1")
            payload["confirmationToken"] = serializer.dumps({
                "materialId": slide_id,
                "graph": repository.material_artifact_reference_fingerprint(slide_id),
                "actor": str(current_actor.get("username") or ""),
            })
            payload["confirmationText"] = str(payload.get("title") or slide_id)
        return jsonify(payload)

    def api_material_purge(slide_id):
        denied = require_admin()
        if denied:
            return denied
        current_actor = actor() or {}
        roles = set(current_actor.get("roles") or [])
        if str(current_actor.get("role") or ""):
            roles.add(str(current_actor.get("role")))
        if "system_admin" not in roles:
            return jsonify({"error": "只有系統管理員可以永久清除教材。"}), 403
        body = request.get_json(silent=True) or {}
        token = str(body.get("confirmationToken") or "")
        expected_text = str((repository.get_material(slide_id) or {}).get("title") or slide_id)
        if str(body.get("confirmationText") or "") != expected_text:
            return jsonify({"error": "確認文字不符，拒絕永久清除。"}), 409
        serializer = URLSafeTimedSerializer(str(current_app.secret_key), salt="material-purge-v1")
        try:
            signed = serializer.loads(token, max_age=300)
        except SignatureExpired:
            return jsonify({"error": "永久清除確認已逾時，請重新檢查。"}), 409
        except BadSignature:
            return jsonify({"error": "永久清除確認無效。"}), 409
        if (
            str(signed.get("materialId") or "") != slide_id
            or str(signed.get("actor") or "") != str(current_actor.get("username") or "")
            or str(signed.get("graph") or "") != repository.material_artifact_reference_fingerprint(slide_id)
        ):
            return jsonify({"error": "教材引用狀態已改變，請重新檢查後再永久清除。"}), 409
        try:
            payload = service.purge_material_storage(slide_id, paths=paths, storage_runtime=runtime)
        except ApiError as exc:
            return _legacy_error(exc)
        audit.record_event(
            actor=current_actor, action="material.purge", target_type="material", target_id=slide_id,
            group="", detail={"backend": payload.get("backend", ""), "confirmation": "two-phase"},
        )
        return jsonify(payload)

    def api_list_material_versions(slide_id):
        denied = require_admin()
        if denied:
            return denied
        try:
            return jsonify(service.list_material_versions(slide_id))
        except ApiError as exc:
            return _legacy_error(exc)

    def api_publish_material_version(slide_id):
        denied = require_admin()
        if denied:
            return denied
        before = repository.get_material(slide_id)
        current_actor = actor() or {}
        try:
            payload = service.publish_material_version(
                slide_id,
                request.get_json(silent=True) or {},
                actor_username=str(current_actor.get("username") or ""),
            )
        except ApiError as exc:
            return _legacy_error(exc)
        after = repository.get_material(slide_id)
        detail = {
            "changeReason": str((request.get_json(silent=True) or {}).get("changeReason") or "")[:1000],
            "requiresRetraining": bool(payload.get("requiresRetraining")),
        }
        audit.record_event(
            actor=current_actor,
            action="material.version.publish",
            target_type="material",
            target_id=slide_id,
            group=str((after or before or {}).get("group") or ""),
            before=snapshot(before),
            after=snapshot(after),
            detail=detail,
        )
        if payload.get("requiresRetraining"):
            audit.record_event(
                actor=current_actor,
                action="material.retraining.require",
                target_type="material",
                target_id=slide_id,
                group=str((after or before or {}).get("group") or ""),
                before=snapshot(before),
                after=snapshot(after),
                detail=detail,
            )
        return jsonify(payload), 201

    def api_restore_material_version(slide_id, source_version):
        denied = require_admin()
        if denied:
            return denied
        before = repository.get_material(slide_id)
        current_actor = actor() or {}
        body = request.get_json(silent=True) or {}
        try:
            payload = service.restore_material_version(
                slide_id,
                source_version,
                body,
                actor_username=str(current_actor.get("username") or ""),
            )
        except ApiError as exc:
            return _legacy_error(exc)
        after = repository.get_material(slide_id)
        audit.record_event(
            actor=current_actor,
            action="material.version.restore",
            target_type="material",
            target_id=slide_id,
            group=str((after or before or {}).get("group") or ""),
            before=snapshot(before),
            after=snapshot(after),
            detail={
                "restoredFromVersion": int(source_version),
                "changeReason": str(body.get("changeReason") or "")[:1000],
                "requiresRetraining": bool(payload.get("requiresRetraining")),
            },
        )
        return jsonify(payload), 201

    AI_NARRATIONS_KEPT = 2

    def api_prune_ai_narrations(slide_id):
        """Keep only the newest AI voices of one source material; delete older ones.

        Called by the teacher UI right after a new AI voice finishes so teachers never
        have to clean up piles of old voices (they only see/remove the newest one).
        """
        denied = require_admin()
        if denied:
            return denied
        source = repository.get_material(slide_id)
        if not source:
            return jsonify({"error": "找不到來源教材"}), 404
        voices = [
            item for item in repository.list_uploaded_materials(include_inactive=True)
            if str((item.get("storageMeta") or {}).get("mediaKind") or "") == "ai_narration"
            and str((item.get("storageMeta") or {}).get("sourceMaterialId") or "") == str(slide_id)
        ]
        voices.sort(key=lambda item: (str(item.get("dateAdded") or ""), str(item.get("id") or "")), reverse=True)
        deleted, failed = [], []
        for old in voices[AI_NARRATIONS_KEPT:]:
            old_id = str(old.get("id") or "")
            try:
                service.delete_material(old_id, paths=paths, storage_runtime=runtime)
            except Exception:  # keep going; one stuck file must not block the rest
                failed.append(old_id)
                continue
            deleted.append(old_id)
            audit.record_event(
                actor=actor(),
                action="material.ai_narration.prune",
                target_type="material",
                target_id=old_id,
                group=str(old.get("group") or ""),
                before=snapshot(old),
            )
        return jsonify({"ok": True, "kept": [str(v.get("id") or "") for v in voices[:AI_NARRATIONS_KEPT]], "deleted": deleted, "failed": failed})

    app.add_url_rule("/api/slides", endpoint="api_list_slides", view_func=api_list_slides, methods=["GET"])
    app.add_url_rule("/api/slides/admin", endpoint="api_admin_slides", view_func=api_admin_slides, methods=["GET"])
    app.add_url_rule("/api/slides/<slide_id>", endpoint="api_update_slide", view_func=api_update_slide, methods=["PATCH"])
    app.add_url_rule("/api/slides/<slide_id>", endpoint="api_delete_slide", view_func=api_delete_slide, methods=["DELETE"])
    app.add_url_rule("/api/slides/<slide_id>/prune-ai-narrations", endpoint="api_prune_ai_narrations", view_func=api_prune_ai_narrations, methods=["POST"])
    app.add_url_rule("/api/slides/<slide_id>/purge-readiness", endpoint="api_material_purge_readiness", view_func=api_material_purge_readiness, methods=["GET"])
    app.add_url_rule("/api/slides/<slide_id>/purge", endpoint="api_material_purge", view_func=api_material_purge, methods=["POST"])
    app.add_url_rule("/api/slides/<slide_id>/versions", endpoint="api_list_material_versions", view_func=api_list_material_versions, methods=["GET"])
    app.add_url_rule("/api/slides/<slide_id>/versions", endpoint="api_publish_material_version", view_func=api_publish_material_version, methods=["POST"])
    app.add_url_rule("/api/slides/<slide_id>/versions/<int:source_version>/restore", endpoint="api_restore_material_version", view_func=api_restore_material_version, methods=["POST"])
    app.extensions["teacher_material_catalog_routes_registered"] = True
    return app


__all__ = ["_legacy_error", "register_material_catalog_routes"]
