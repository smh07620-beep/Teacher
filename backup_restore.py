"""Legacy-compatible maintenance HTTP adapter.

Canonical backup/archive/restore behavior lives in ``teacher_app.maintenance.backup``.
This root module preserves existing URLs and test-facing compatibility helpers only.
"""
from __future__ import annotations

import datetime as dt
import io
import os

from flask import jsonify, request, send_file

from teacher_app.common.auth import has_permission, user_roles
from teacher_app.maintenance import backup as maintenance_backup

BACKUP_FORMAT = maintenance_backup.BACKUP_FORMAT
DEFAULT_TABLES = maintenance_backup.DEFAULT_TABLES
utcnow = maintenance_backup.utcnow
app_version = maintenance_backup.app_version
_zip_payload = maintenance_backup.zip_payload
_compatible_restore_row = maintenance_backup.compatible_restore_row


def _auth(base, allowed):
    """Compatibility auth adapter; capability checks are canonical-first."""
    user = base._current_user()
    if not user:
        return None, (jsonify({"error": "請先登入。"}), 401)

    allowed_roles = {base.normalize_role(role) for role in allowed}
    role_allowed = any(role in allowed_roles for role in user_roles(user))
    capability_allowed = (
        has_permission(user, "backup.manage")
        or has_permission(user, "education.cross_group.manage")
    )
    if not (role_allowed or capability_allowed):
        return None, (jsonify({"error": "權限不足。"}), 403)
    return user, None


def build_backup(base):
    """Legacy signature; canonical implementation receives only a DB seam."""
    return maintenance_backup.build_backup(base._db_conn)


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


def _restore(base, payload):
    """Legacy signature; canonical implementation owns the transaction."""
    return maintenance_backup.restore_backup(payload, base._db_conn)


def _purge_teacher_mega_root(base):
    """Destroy only the configured Teacher MEGA root, never the account root."""
    root_name = str(getattr(base, "MEGA_ROOT_FOLDER", "") or "").strip().strip("/")
    if not root_name or root_name in {".", ".."}:
        raise RuntimeError("MEGA_ROOT_FOLDER 不安全，拒絕清除。")
    root = str(base._mega_root_id() or "").strip()
    if root.strip("/") != root_name:
        raise RuntimeError("MEGA root 驗證失敗，拒絕清除非 Teacher 目錄。")
    base.mega_destroy(root)
    return root_name


def register_backup_restore(base):
    app = base.app
    if app.extensions.get("teacher_backup_restore_registered"):
        return app
    app.extensions["teacher_backup_restore_registered"] = True

    @app.get("/api/maintenance/backup")
    def teacher_backup_download():
        _user, denied = _auth(base, {"education_admin", "system_admin"})
        if denied:
            return denied
        payload = build_backup(base)
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
        _user, denied = _auth(base, {"education_admin", "system_admin"})
        if denied:
            return denied
        if str(request.form.get("confirm", "")) != "RESTORE":
            return jsonify({"error": "還原前請輸入 RESTORE 確認。"}), 400
        try:
            payload = _read_backup_upload()
            restored = _restore(base, payload)
            return jsonify({
                "ok": True,
                "restored": restored,
                "backupCreatedAt": payload.get("createdAt", ""),
            })
        except Exception as exc:
            return jsonify({"error": str(exc)[:500]}), 400

    @app.post("/api/maintenance/storage/mega/purge-root")
    def teacher_mega_purge_root():
        user = base._current_user()
        if not user:
            return jsonify({"error": "請先登入。"}), 401
        if not has_permission(user, "system.manage"):
            return jsonify({"error": "權限不足：僅系統管理者可清空 Teacher MEGA 根目錄。"}), 403
        data = request.get_json(silent=True) or request.form
        if str(data.get("confirm", "")) != "PURGE-MEGA":
            return jsonify({"error": "清空前必須以 PURGE-MEGA 確認。"}), 400
        try:
            root_name = _purge_teacher_mega_root(base)
            return jsonify({"ok": True, "purgedRoot": root_name})
        except Exception as exc:
            return jsonify({"error": str(exc)[:500]}), 502

    return app
