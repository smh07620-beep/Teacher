"""Legacy-compatible maintenance HTTP adapter.

Canonical backup/archive/restore behavior lives in ``teacher_app.maintenance.backup``.
This root module preserves existing URLs and test-facing compatibility helpers only.
"""
from __future__ import annotations

import datetime as dt
import io
import os

from flask import g, has_request_context, jsonify, request, send_file

from teacher_app.common import audit, db as common_db
from teacher_app.common.auth import has_permission, normalize_role, user_roles
from teacher_app.maintenance import backup as maintenance_backup
from teacher_app.storage import providers
from teacher_app.storage.web_runtime import WebStorageRuntime

BACKUP_FORMAT = maintenance_backup.BACKUP_FORMAT
DEFAULT_TABLES = maintenance_backup.DEFAULT_TABLES
utcnow = maintenance_backup.utcnow
app_version = maintenance_backup.app_version
_zip_payload = maintenance_backup.zip_payload
_compatible_restore_row = maintenance_backup.compatible_restore_row
_DEFAULT_CONNECTION_FACTORY = object()


def _auth(owner, allowed):
    """Compatibility auth adapter; capability checks are canonical-first."""
    user = getattr(g, "teacher_user", None) if has_request_context() else None
    if user is None:
        resolver = getattr(owner, "_current_user", None)
        if callable(resolver):
            user = resolver()
    if not user:
        return None, (jsonify({"error": "請先登入。"}), 401)

    allowed_roles = {normalize_role(role) for role in allowed}
    role_allowed = any(role in allowed_roles for role in user_roles(user))
    capability_allowed = (
        has_permission(user, "backup.manage")
        or has_permission(user, "education.cross_group.manage")
    )
    if not (role_allowed or capability_allowed):
        return None, (jsonify({"error": "權限不足。"}), 403)
    return user, None


def _connection_factory(value=None):
    """Accept a direct factory; legacy base objects remain test/plugin compatible."""
    if value is None or callable(value):
        return value
    return getattr(value, "_db_conn")


def build_backup(connection_factory=None):
    return maintenance_backup.build_backup(_connection_factory(connection_factory))


def _read_backup_upload():
    upload = request.files.get("file")
    if not upload:
        raise ValueError("請上傳備份 ZIP。")
    max_mb = max(1, min(500, int(os.environ.get("BACKUP_MAX_UPLOAD_MB", "100"))))
    raw = upload.read(max_mb * 1024 * 1024 + 1)
    if len(raw) > max_mb * 1024 * 1024:
        raise ValueError("備份檔超過允許大小。")
    max_expanded_mb = max(1, min(2048, int(os.environ.get("BACKUP_MAX_EXPANDED_MB", "500"))))
    return maintenance_backup.parse_backup_zip(raw, max_expanded_mb=max_expanded_mb)


def _restore(connection_factory_or_payload, payload=None):
    """Canonical restore accepts a DB factory; keep the old two-arg call shape."""
    if payload is None:
        return maintenance_backup.restore_backup(connection_factory_or_payload)
    return maintenance_backup.restore_backup(
        payload,
        _connection_factory(connection_factory_or_payload),
    )


def _purge_teacher_mega_root(runtime):
    """Destroy only the configured Teacher MEGA root, never the account root."""
    root_name = str(getattr(runtime, "MEGA_ROOT_FOLDER", None) or providers.MEGA_ROOT_FOLDER or "").strip().strip("/")
    if not root_name or root_name in {".", ".."}:
        raise RuntimeError("MEGA_ROOT_FOLDER 不安全，拒絕清除。")
    root_resolver = getattr(runtime, "mega_root", None) or getattr(runtime, "_mega_root_id", None)
    if not callable(root_resolver):
        raise RuntimeError("MEGA root runtime 未設定。")
    root = str(root_resolver() or "").strip()
    if root.strip("/") != root_name:
        raise RuntimeError("MEGA root 驗證失敗，拒絕清除非 Teacher 目錄。")
    legacy_destroy = getattr(runtime, "mega_destroy", None)
    if callable(legacy_destroy):
        legacy_destroy(root)
    else:
        providers.mega_delete_object(
            root,
            is_configured=runtime.storage.mega_is_configured,
            run=runtime.storage._mega_run,
        )
    return root_name


def register_backup_restore(owner, *, connection_factory=_DEFAULT_CONNECTION_FACTORY, paths=None, storage_runtime=None):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_backup_restore_registered"):
        return app
    app.extensions["teacher_backup_restore_registered"] = True
    if connection_factory is _DEFAULT_CONNECTION_FACTORY:
        connection_factory = getattr(owner, "_db_conn", None) if owner is not app else None
    if connection_factory is None:
        connection_factory = common_db.get_connection
    paths = paths or app.config.get("STORAGE_PATHS")
    runtime = storage_runtime or (WebStorageRuntime(paths) if paths is not None else None)

    @app.get("/api/maintenance/backup")
    def teacher_backup_download():
        user, denied = _auth(owner, {"education_admin", "system_admin"})
        if denied:
            return denied
        payload = build_backup(connection_factory)
        audit.record_event(
            actor=user,
            action="backup.export",
            target_type="backup",
            target_id=str(payload.get("createdAt") or ""),
            detail={
                "format": payload.get("format", ""),
                "createdAt": payload.get("createdAt", ""),
                "tableCount": len(payload.get("tables") or {}),
                "tables": sorted((payload.get("tables") or {}).keys()),
            },
        )
        data = _zip_payload(payload)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        return send_file(
            io.BytesIO(data),
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"teacher-backup-{stamp}.zip",
        )

    @app.post("/api/maintenance/restore")
    def teacher_backup_restore():
        user, denied = _auth(owner, {"education_admin", "system_admin"})
        if denied:
            return denied
        if str(request.form.get("confirm", "")) != "RESTORE":
            return jsonify({"error": "還原前請輸入 RESTORE 確認。"}), 400
        try:
            payload = _read_backup_upload()
            restored = maintenance_backup.restore_backup(payload, connection_factory)
            audit.record_event(
                actor=user,
                action="backup.restore",
                target_type="backup",
                target_id=str(payload.get("createdAt") or ""),
                detail={
                    "format": payload.get("format", ""),
                    "backupCreatedAt": payload.get("createdAt", ""),
                    "restored": restored,
                },
            )
            return jsonify({
                "ok": True,
                "restored": restored,
                "backupCreatedAt": payload.get("createdAt", ""),
            })
        except Exception as exc:
            return jsonify({"error": str(exc)[:500]}), 400

    @app.post("/api/maintenance/storage/mega/purge-root")
    def teacher_mega_purge_root():
        user = getattr(g, "teacher_user", None) if has_request_context() else None
        if user is None:
            resolver = getattr(owner, "_current_user", None)
            if callable(resolver):
                user = resolver()
        if not user:
            return jsonify({"error": "請先登入。"}), 401
        if not has_permission(user, "system.manage"):
            return jsonify({"error": "權限不足：僅系統管理者可清空 Teacher MEGA 根目錄。"}), 403
        data = request.get_json(silent=True) or request.form
        if str(data.get("confirm", "")) != "PURGE-MEGA":
            return jsonify({"error": "清空前必須以 PURGE-MEGA 確認。"}), 400
        try:
            if runtime is None:
                return jsonify({"error": "StoragePaths 尚未設定。"}), 503
            root_name = _purge_teacher_mega_root(runtime)
            return jsonify({"ok": True, "purgedRoot": root_name})
        except Exception as exc:
            return jsonify({"error": str(exc)[:500]}), 502

    return app
