"""Canonical PGY assessment-center HTTP routes."""
from __future__ import annotations

import uuid
from pathlib import Path

import requests
from flask import g, jsonify, request

from teacher_app.common.auth import has_permission, require_role
from teacher_app.common.errors import ApiError
from teacher_app.pgy import assessments
from teacher_app.pgy.template_runtime import PgyTemplateRuntime


def _current_user():
    return getattr(g, "teacher_user", None)


def _require_admin():
    user = _current_user()
    if not user:
        return jsonify({
            "error": "請先以管理者帳號登入。",
            "loginRequired": True,
        }), 401
    if not has_permission(user, "template.manage"):
        return jsonify({"error": "權限不足：此功能限教學管理者使用。"}), 403
    return None


def _require_roles(*allowed_roles):
    try:
        return require_role(_current_user(), *allowed_roles), None
    except ApiError as exc:
        body = {"error": exc.message}
        body.update(exc.extra)
        if exc.code == "LOGIN_REQUIRED":
            body["loginRequired"] = True
        return None, (jsonify(body), exc.status)


def register_pgy_assessment_routes(owner, *, paths, template_runtime=None):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_pgy_assessment_routes_registered"):
        return app
    runtime = template_runtime or PgyTemplateRuntime(paths)

    def material_login_user():
        user = _current_user()
        if not user:
            return None, (jsonify({"error": "請先登入後再使用教材。", "loginRequired": True}), 401)
        return user, None

    def api_pgy_assessment_templates():
        _user, denied = material_login_user()
        if denied:
            return denied
        return jsonify(assessments.list_templates())

    def api_upload_pgy_assessment_template(template_type):
        denied = _require_admin()
        if denied:
            return denied
        if template_type not in assessments.PGY_ASSESSMENT_TYPES:
            return jsonify({"error": "不支援的評量範本類型"}), 400
        upload = request.files.get("file")
        if not upload or not upload.filename:
            return jsonify({"error": "請選擇檔案"}), 400
        ext = Path(upload.filename).suffix.lower()
        if ext not in {".docx", ".pdf"}:
            return jsonify({"error": "評量範本僅接受 .docx 或 .pdf"}), 400
        tmp = paths.tmp_dir / f"pgy-template-{template_type}-{uuid.uuid4().hex}{ext}"
        upload.save(tmp)
        try:
            validation = runtime.validate(tmp, ext)
            old = assessments.get_template(template_type)
            backend, key = runtime.store(tmp, template_type, upload.filename)
            assessments.save_template(template_type, upload.filename, backend, key)
            if old and (old.get("storage_key") or "") != key:
                runtime.delete(old)
            return jsonify({"ok": True, "templateType": template_type, "storageBackend": backend, "validation": validation})
        except ValueError as exc:
            return jsonify({"error": f"範本檢查失敗：{exc}"}), 400
        except Exception as exc:
            app.logger.exception("PGY template upload failed")
            return jsonify({"error": f"評量範本上傳失敗：{exc}"}), 500
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

    def api_import_tslm_epa_template():
        denied = _require_admin()
        if denied:
            return denied
        tmp = paths.tmp_dir / f"tslm-epa-{uuid.uuid4().hex}.pdf"
        try:
            response = requests.get(
                assessments.TSLM_EPA_REFERENCE_URL,
                timeout=45,
                headers={"User-Agent": "SMH-Teaching-Portal/1.0"},
            )
            response.raise_for_status()
            tmp.write_bytes(response.content)
            validation = runtime.validate(tmp, ".pdf")
            old = assessments.get_template("epa_reference")
            filename = "台灣醫事檢驗學會_醫事檢驗職類_EPAs_第一版.pdf"
            backend, key = runtime.store(tmp, "epa_reference", filename)
            assessments.save_template("epa_reference", filename, backend, key, assessments.TSLM_EPA_REFERENCE_URL)
            if old and (old.get("storage_key") or "") != key:
                runtime.delete(old)
            return jsonify({"ok": True, "storageBackend": backend, "sourceUrl": assessments.TSLM_EPA_REFERENCE_URL, "validation": validation})
        except Exception as exc:
            return jsonify({"error": f"匯入學會 EPA 公版失敗：{exc}"}), 502
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

    def api_download_pgy_assessment_template(template_type):
        _user, denied = material_login_user()
        if denied:
            return denied
        row = assessments.get_template(template_type)
        if not row:
            return jsonify({"error": "尚未設定此評量範本"}), 404
        return runtime.send(row, inline=True)

    def api_delete_pgy_assessment_template(template_type):
        denied = _require_admin()
        if denied:
            return denied
        row = assessments.get_template(template_type)
        if not row:
            return jsonify({"ok": True})
        try:
            runtime.delete(row, best_effort=False)
        except Exception as exc:
            cause = getattr(exc, "cause", exc)
            return jsonify({"error": f"評量範本刪除失敗：{cause}"}), 502
        assessments.delete_template(template_type)
        return jsonify({"ok": True})

    def api_create_pgy_assessment():
        user, denied = _require_roles("clinical_teacher")
        if denied:
            return denied
        try:
            record_id = assessments.create_assessment(user, request.get_json(silent=True) or {})
        except assessments.AssessmentError as exc:
            return jsonify({"error": str(exc)}), exc.status
        return jsonify({"ok": True, "id": record_id})

    def api_list_pgy_assessments():
        user = _current_user()
        try:
            result = assessments.list_assessments(
                user,
                emp_id=str(request.args.get("emp_id", "")).strip(),
                group=(str(request.args.get("group", "")).strip() if "group" in request.args else None),
                admin_override=False,
            )
        except assessments.AssessmentError as exc:
            body = {"error": str(exc)}
            if exc.status == 401:
                body["loginRequired"] = True
            return jsonify(body), exc.status
        return jsonify(result)

    for rule, endpoint, view, methods in (
        ("/api/pgy-assessment-templates", "api_pgy_assessment_templates", api_pgy_assessment_templates, ["GET"]),
        ("/api/pgy-assessment-templates/<template_type>", "api_upload_pgy_assessment_template", api_upload_pgy_assessment_template, ["POST"]),
        ("/api/pgy-assessment-templates/import-tslm-epa", "api_import_tslm_epa_template", api_import_tslm_epa_template, ["POST"]),
        ("/api/pgy-assessment-templates/<template_type>/download", "api_download_pgy_assessment_template", api_download_pgy_assessment_template, ["GET"]),
        ("/api/pgy-assessment-templates/<template_type>", "api_delete_pgy_assessment_template", api_delete_pgy_assessment_template, ["DELETE"]),
        ("/api/pgy-assessments", "api_create_pgy_assessment", api_create_pgy_assessment, ["POST"]),
        ("/api/pgy-assessments", "api_list_pgy_assessments", api_list_pgy_assessments, ["GET"]),
    ):
        app.add_url_rule(rule, endpoint=endpoint, view_func=view, methods=methods)

    app.extensions["teacher_pgy_assessment_routes_registered"] = True
    return app


__all__ = ["register_pgy_assessment_routes"]
