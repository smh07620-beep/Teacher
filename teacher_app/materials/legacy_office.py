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

from teacher_app.common import scope, scope_filter
from teacher_app.materials import repository as material_repository


OFFICE_EXTENSIONS = {
    ".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx",
    ".odp", ".odt", ".ods",
}


def _material_group(entry):
    return str(
        (entry or {}).get("group")
        or (entry or {}).get("groupKey")
        or (entry or {}).get("group_key")
        or scope.DEFAULT_GROUP
        or ""
    ).strip()


def _authorize_material_manager(owner, app, entry):
    """Authorize through canonical RBAC, retaining isolated-fixture fallback."""
    if owner is not app:
        compat = getattr(owner, "require_scoped_permission", None)
        if callable(compat):
            return compat("material.manage", _material_group(entry))
    return scope_filter.scoped_groups(app, "material.manage", {_material_group(entry)})[1]


def register_legacy_office_69(owner, *, material_getter=None):
    app = getattr(owner, "app", owner)
    get_material = material_getter
    if get_material is None and owner is not app:
        get_material = getattr(owner, "get_material", None)
    get_material = get_material or material_repository.get_material
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
        entry = get_material(slide_id)
        if not entry or not entry.get("active"):
            abort(404)

        extension = Path(str(entry.get("filename") or "")).suffix.lower()
        if extension not in OFFICE_EXTENSIONS:
            return original_download(slide_id)

        # Office source files are not a normal teaching surface.  A teacher who
        # can manage this material still receives only its safe preview.
        denied = _authorize_material_manager(owner, app, entry)
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
