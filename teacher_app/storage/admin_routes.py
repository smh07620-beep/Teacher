"""Canonical HTTP routes for storage administration."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common.auth import has_permission
from teacher_app.storage import admin_service


def _app(owner):
    return getattr(owner, "app", owner)


def _current_user(owner=None):
    if hasattr(g, "teacher_user"):
        return g.teacher_user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _require_admin(owner=None):
    user = _current_user(owner)
    if not user:
        return jsonify({
            "error": "請先以管理者帳號登入。",
            "loginRequired": True,
        }), 401
    if not has_permission(user, "storage.manage"):
        return jsonify({"error": "權限不足：此功能限教學管理者使用。"}), 403
    return None


def _bind_rule(app, rule: str, endpoint: str, view_func, methods: list[str]) -> None:
    """Replace copied legacy views now, while remaining add-rule compatible later."""
    if endpoint in app.view_functions:
        app.view_functions[endpoint] = view_func
        return
    app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=methods)


def register_storage_admin_routes(
    owner,
    *,
    paths=None,
    paths_provider=None,
    runtime: admin_service.StorageAdminRuntime | None = None,
    r2_record_object=None,
    r2_record_deleted=None,
):
    app = _app(owner)
    if app.extensions.get("teacher_storage_admin_routes_registered"):
        return app

    if runtime is None:
        resolved_paths = paths or app.config.get("STORAGE_PATHS")
        if resolved_paths is None and paths_provider is None:
            raise RuntimeError("StoragePaths is required for storage-admin routes")
        provider = paths_provider or (lambda: resolved_paths)
        runtime = admin_service.build_canonical_runtime(
            paths_provider=provider,
            r2_record_object=r2_record_object,
            r2_record_deleted=r2_record_deleted,
        )

    def api_storage_status():
        denied = _require_admin(owner)
        if denied:
            return denied
        force = request.args.get("refresh", "").strip().lower() in {"1", "true", "yes"}
        return jsonify(admin_service.storage_status(runtime, force=force))

    def api_migrate_materials_to_gdrive():
        denied = _require_admin(owner)
        if denied:
            return denied
        payload, status = admin_service.migrate_materials_to_gdrive(runtime)
        return jsonify(payload), status

    def api_migrate_materials_to_r2():
        denied = _require_admin(owner)
        if denied:
            return denied
        payload, status = admin_service.migrate_materials_to_r2(runtime)
        return jsonify(payload), status

    _bind_rule(app, "/api/storage-status", "api_storage_status", api_storage_status, ["GET"])
    _bind_rule(
        app,
        "/api/storage/migrate-to-gdrive",
        "api_migrate_materials_to_gdrive",
        api_migrate_materials_to_gdrive,
        ["POST"],
    )
    _bind_rule(
        app,
        "/api/storage/migrate-to-r2",
        "api_migrate_materials_to_r2",
        api_migrate_materials_to_r2,
        ["POST"],
    )
    app.extensions["teacher_storage_admin_routes_registered"] = True
    return app


__all__ = ["register_storage_admin_routes"]
