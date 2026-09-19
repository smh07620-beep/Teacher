"""Thin HTTP compatibility adapter for synchronous material upload."""
from __future__ import annotations

from flask import jsonify, request

from teacher_app.auth import rbac_legacy_adapter
from teacher_app.materials import sync_upload
from teacher_app.materials import sync_runtime


def _app(owner):
    return getattr(owner, "app", owner)


def register_sync_upload_routes(
    owner,
    *,
    paths=None,
    paths_provider=None,
    runtime=None,
    r2_record_object=None,
    r2_record_deleted=None,
):
    app = _app(owner)
    if app.extensions.get("teacher_sync_upload_routes_registered"):
        return app
    if runtime is None:
        resolved = paths or app.config.get("STORAGE_PATHS")
        if resolved is None and paths_provider is None:
            raise RuntimeError("StoragePaths is required for synchronous upload")
        provider = paths_provider or (lambda: resolved)
        runtime = sync_runtime.build_canonical_sync_runtime(
            paths_provider=provider,
            r2_record_object=r2_record_object,
            r2_record_deleted=r2_record_deleted,
        )

    def require_admin():
        # Isolated compatibility fixtures historically install only a local
        # require_admin function. Production has canonical request/RBAC binding.
        if not app.extensions.get("teacher_rbac_681_registered"):
            compat = getattr(owner, "require_admin", None)
            if callable(compat):
                return compat()
        return rbac_legacy_adapter.legacy_admin_guard(app)

    def api_upload_slide():
        denied = require_admin()
        if denied:
            return denied
        if "file" not in request.files:
            return jsonify({"error": "未收到檔案"}), 400
        try:
            return jsonify(sync_upload.process_upload(request.files["file"], request.form, runtime))
        except sync_upload.SyncUploadError as exc:
            return jsonify(exc.body), exc.status

    if "api_upload_slide" in app.view_functions:
        app.view_functions["api_upload_slide"] = api_upload_slide
    else:
        app.add_url_rule(
            "/api/slides/upload",
            endpoint="api_upload_slide",
            view_func=api_upload_slide,
            methods=["POST"],
        )
    app.extensions["teacher_sync_upload_routes_registered"] = True
    return app


__all__ = ["register_sync_upload_routes"]
