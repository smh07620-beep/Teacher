"""Canonical `/system` shell and learner Office-view safety boundary."""
from __future__ import annotations

from pathlib import Path

from flask import abort, g, jsonify, redirect, request, send_from_directory

from teacher_app.common.auth import has_role, is_teacher_workspace_user
from teacher_app.common import scope_filter
from teacher_app.materials import repository as material_repository


OFFICE_EXTENSIONS = {
    ".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx", ".odp", ".odt", ".ods",
}


def register_system_page(owner):
    app = getattr(owner, "app", owner)

    def system_page():
        user = getattr(g, "teacher_user", None)
        if not user:
            return redirect("/login?next=/system")
        if request.args.get("admin") == "1" and not is_teacher_workspace_user(user):
            return jsonify({"error": "學生不能進入管理區。"}), 403
        return send_from_directory(app.static_folder, "system.html")

    for rule in app.url_map.iter_rules():
        if rule.rule == "/system" and "GET" in rule.methods:
            app.view_functions[rule.endpoint] = system_page

    def learner_office_view(material_id):
        entry = material_repository.get_material(material_id)
        if not entry or not entry.get("active"):
            abort(404)
        user = getattr(g, "teacher_user", None)
        extension = Path(str(entry.get("filename") or "")).suffix.lower()
        if extension in OFFICE_EXTENSIONS and has_role(user, "student"):
            meta = entry.get("storageMeta") or {}
            if meta.get("previewMode") == "single_pdf":
                return redirect(f"/material-preview/{material_id}", code=302)
            return jsonify({
                "error": "教材預覽尚未完成，請管理者重新處理。",
                "previewRequired": True,
            }), 409
        if extension in OFFICE_EXTENSIONS:
            denied = scope_filter.scoped_groups(
                app,
                "material.manage",
                {scope_filter.row_group(entry)},
            )[1]
            if denied:
                return denied
        return app.extensions["teacher_legacy_view_material"](material_id)

    for rule in app.url_map.iter_rules():
        if rule.rule == "/view/<material_id>" and "GET" in rule.methods:
            app.extensions["teacher_legacy_view_material"] = app.view_functions[rule.endpoint]
            app.view_functions[rule.endpoint] = learner_office_view


__all__ = ["OFFICE_EXTENSIONS", "register_system_page"]
