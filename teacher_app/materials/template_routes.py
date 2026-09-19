"""Canonical HTTP routes for group-specific Word export templates."""
from __future__ import annotations

import uuid
from pathlib import Path

from flask import g, jsonify, redirect, request, send_file

from teacher_app.common import scope
from teacher_app.common.auth import has_permission
from teacher_app.materials import template_runtime as template_runtime_module, templates
from teacher_app.storage import StorageDeletionError


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
    if not has_permission(user, "template.manage"):
        return jsonify({"error": "權限不足：此功能限教學管理者使用。"}), 403
    return None


def register_doc_template_routes(
    owner,
    *,
    paths,
    runtime: template_runtime_module.DocumentTemplateRuntime | None = None,
    r2_record_object=None,
):
    app = _app(owner)
    if app.extensions.get("teacher_doc_template_routes_registered"):
        return app
    runtime = runtime or template_runtime_module.DocumentTemplateRuntime(
        paths,
        r2_record_object=r2_record_object,
    )

    def api_list_doc_templates():
        rows = templates.list_templates()
        return jsonify([
            {
                "group": group,
                "label": label,
                "exists": group in rows,
                "filename": rows.get(group, {}).get("filename", ""),
                "uploadedAt": rows.get(group, {}).get("uploaded_at", ""),
                "storageBackend": rows.get(group, {}).get("storage_backend", "local") or "local",
            }
            for group, label in scope.GROUPS.items()
        ])

    def api_upload_doc_template(group_key):
        denied = _require_admin(owner)
        if denied:
            return denied
        if group_key not in scope.GROUPS:
            return jsonify({"error": "無效的組別代碼"}), 400
        if "file" not in request.files:
            return jsonify({"error": "缺少檔案"}), 400
        upload = request.files["file"]
        original_name = upload.filename or "附件1.docx"
        ext = Path(original_name).suffix.lower()
        if ext not in templates.DOC_TEMPLATE_ALLOWED_EXT:
            return jsonify({"error": "僅接受 .docx 檔案"}), 400
        old = templates.get_template(group_key)
        storage_filename = f"{group_key}.docx"
        tmp_path = paths.tmp_dir / f"doc-template-{group_key}-{uuid.uuid4().hex[:8]}.docx"
        backend = "local"
        storage_key = ""
        storage_created = False
        try:
            upload.save(str(tmp_path))
            validation = runtime.validate(tmp_path, ext)
            backend, storage_key = runtime.store(tmp_path, group_key, storage_filename)
            storage_created = True

            if old:
                old_backend = str(old.get("storage_backend") or "local").lower()
                old_key = str(old.get("storage_key") or "")
                should_cleanup = (
                    (old_backend == "local" and backend != "local")
                    or (old_backend != "local" and bool(old_key) and old_key != storage_key)
                )
                if should_cleanup:
                    cleanup = runtime.delete(old, best_effort=True)
                    if cleanup is not None and not cleanup.deleted:
                        app.logger.warning("old doc template cleanup failed: %s", cleanup.error)

            templates.save_template(
                group_key,
                original_name,
                storage_filename,
                backend,
                storage_key,
            )
            return jsonify({
                "ok": True,
                "group": group_key,
                "filename": original_name,
                "storageBackend": backend,
                "validation": validation,
            })
        except ValueError as exc:
            return jsonify({"error": f"Word 範本檢查失敗：{exc}", "stage": "範本內容驗證"}), 400
        except Exception as exc:
            app.logger.exception("doc template upload failed")
            old_local_same_path = bool(
                old
                and backend == "local"
                and str(old.get("storage_backend") or "local").lower() == "local"
                and str(old.get("storage_filename") or storage_filename) == storage_filename
            )
            if storage_created and not old_local_same_path:
                orphan = runtime.delete(
                    {
                        "storage_backend": backend,
                        "storage_key": storage_key,
                        "storage_filename": storage_filename,
                    },
                    best_effort=True,
                )
                if orphan is not None and not orphan.deleted:
                    app.logger.warning("orphan doc template cleanup failed: %s", orphan.error)
            return jsonify({"error": f"Word 範本上傳失敗：{exc}"}), 500
        finally:
            tmp_path.unlink(missing_ok=True)

    def api_download_doc_template(group_key):
        row = templates.get_template(group_key)
        if not row:
            return jsonify({"error": "此組別尚未上傳 Word 匯出範本"}), 404
        backend = str(row.get("storage_backend") or "local").lower()
        key = str(row.get("storage_key") or "")
        if backend == "mega":
            if not runtime.configured("mega"):
                return jsonify({"error": "MEGA 尚未設定完成，無法讀取 Word 範本"}), 503
            try:
                return runtime.send(row, inline=True)
            except Exception as exc:
                return jsonify({"error": f"MEGA 讀取 Word 範本失敗：{exc}"}), 502
        if backend == "oci":
            if not runtime.configured("oci"):
                return jsonify({"error": "Oracle Object Storage 尚未設定完成，無法讀取 Word 範本"}), 503
            return redirect(runtime.send(row, inline=True))
        if backend == "gdrive":
            if not runtime.configured("gdrive"):
                return jsonify({"error": "Google Drive 尚未設定完成，無法讀取 Word 範本"}), 503
            return runtime.send(row, inline=True)
        if backend == "r2":
            if not runtime.configured("r2"):
                return jsonify({"error": "Cloudflare R2 尚未設定完成，無法讀取 Word 範本"}), 503
            return redirect(runtime.send(row, inline=True))
        path = runtime.send(row, inline=True)
        if not path.exists():
            return jsonify({"error": "範本檔案遺失，請管理者重新上傳"}), 404
        return send_file(path, as_attachment=False, download_name=row["filename"])

    def api_delete_doc_template(group_key):
        denied = _require_admin(owner)
        if denied:
            return denied
        row = templates.get_template(group_key)
        if row:
            try:
                runtime.delete(row, best_effort=False)
            except Exception as exc:
                cause = exc.cause if isinstance(exc, StorageDeletionError) else exc
                return jsonify({"error": f"Word 範本刪除失敗：{cause}"}), 502
            templates.delete_template(group_key)
        return jsonify({"ok": True})

    app.add_url_rule("/api/doc-templates", endpoint="api_list_doc_templates", view_func=api_list_doc_templates, methods=["GET"])
    app.add_url_rule("/api/doc-templates/<group_key>", endpoint="api_upload_doc_template", view_func=api_upload_doc_template, methods=["POST"])
    app.add_url_rule("/api/doc-templates/<group_key>/download", endpoint="api_download_doc_template", view_func=api_download_doc_template, methods=["GET"])
    app.add_url_rule("/api/doc-templates/<group_key>", endpoint="api_delete_doc_template", view_func=api_delete_doc_template, methods=["DELETE"])
    app.extensions["teacher_doc_template_routes_registered"] = True
    return app


__all__ = ["register_doc_template_routes"]
