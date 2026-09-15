"""Teacher 6.9 legacy Office download retirement.

The old ``/download/<slide_id>`` route predates the current preview pipeline and
can expose an original Office source when a caller reaches the management
endpoint.  Normal teaching workflows should never need the original .pptx,
.docx, .xlsx, ODF, etc. source; they should use the generated preview instead.

This adapter leaves non-Office legacy downloads untouched, but intercepts
Office downloads after RBAC has been registered:

* the caller must have ``material.manage`` for the material's group;
* a single-PDF preview redirects to the safe preview route;
* a converted/page-based Office material returns a clear 409 telling the UI to
  open it through the material reader instead of leaking the source file.

Server-side RBAC remains authoritative.  ``professional_title`` and
``responsibility_tags`` are display metadata and are intentionally not used
here.
"""
from __future__ import annotations

from pathlib import Path

from flask import abort, jsonify, redirect


OFFICE_EXTENSIONS = {
    ".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx",
    ".odp", ".odt", ".ods",
}


def _material_group(base, entry):
    return str(
        (entry or {}).get("group")
        or (entry or {}).get("groupKey")
        or (entry or {}).get("group_key")
        or getattr(base, "DEFAULT_GROUP", "")
        or ""
    ).strip()


def _authorize_material_manager(base, entry):
    """Authorize through canonical RBAC, falling back only for old deployments."""
    if hasattr(base, "require_scoped_permission"):
        return base.require_scoped_permission("material.manage", _material_group(base, entry))
    return base.require_admin()


def register_legacy_office_69(base):
    app = base.app
    if app.extensions.get("teacher_legacy_office_69_registered"):
        return app

    legacy_endpoint = None
    for rule in app.url_map.iter_rules():
        if rule.rule == "/download/<slide_id>" and "GET" in rule.methods:
            legacy_endpoint = rule.endpoint
            break

    # Some unit-test/minimal builds may not expose the old endpoint.  Treat that
    # as already safe instead of failing application startup.
    if not legacy_endpoint:
        app.extensions["teacher_legacy_office_69_registered"] = True
        return app

    original_download = app.view_functions[legacy_endpoint]
    app.extensions["teacher_legacy_download_material"] = original_download

    def safe_download_material(slide_id):
        entry = base.get_material(slide_id)
        if not entry or not entry.get("active"):
            abort(404)

        extension = Path(str(entry.get("filename") or "")).suffix.lower()
        if extension not in OFFICE_EXTENSIONS:
            return original_download(slide_id)

        # Office source files are not a normal teaching surface.  A teacher who
        # can manage this material still receives only its safe preview.
        denied = _authorize_material_manager(base, entry)
        if denied:
            return denied

        storage_meta = entry.get("storageMeta") or {}
        if storage_meta.get("previewMode") == "single_pdf":
            return redirect(f"/material-preview/{slide_id}", code=302)

        # Older Office materials may have image/page previews rather than a
        # single preview PDF.  Do not fall through to the original source.  The
        # normal material reader already knows how to render those pages.
        return jsonify({
            "error": "Office 原始檔下載已停用，請由教材閱讀器開啟此教材。",
            "previewRequired": True,
            "materialId": slide_id,
        }), 409

    app.view_functions[legacy_endpoint] = safe_download_material
    app.extensions["teacher_legacy_office_69_registered"] = True
    return app
