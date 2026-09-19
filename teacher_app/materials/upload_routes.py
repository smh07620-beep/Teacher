"""Canonical Flask registration for material upload validation."""
from __future__ import annotations

from flask import jsonify, request

from teacher_app.materials.validation import validate_filestorage


def register_upload_hardening(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_upload_hardening_registered"):
        return app
    app.extensions["teacher_upload_hardening_registered"] = True

    @app.before_request
    def validate_uploaded_files():
        if request.method not in {"POST", "PUT", "PATCH"} or not request.files:
            return None
        try:
            for storage in request.files.values():
                validate_filestorage(storage)
        except Exception as exc:
            return jsonify({"error": f"上傳檔案安全檢查失敗：{str(exc)[:400]}"}), 400
        return None

    return app


__all__ = ["register_upload_hardening"]
