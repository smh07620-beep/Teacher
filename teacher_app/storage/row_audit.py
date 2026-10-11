"""Read-only inventory of every stored material row, with a usage verdict.

The storage card only shows counts per backend.  Rows that the normal material
lists hide (teacher/AI narration audio folded into its source material, rows whose
source was deleted, disabled rows, rows linked to no course) still count there, so
"MEGA 2" could not be traced.  This lists each row and says why it exists.

Nothing is changed here.  Removal goes through the existing audited material
delete endpoint.
"""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common.auth import has_permission

NARRATION_KINDS = {"teacher_narration", "ai_narration"}

# status -> (label, needs attention)
STATUS = {
    "orphan_narration": ("孤兒旁白：所屬教材已不存在", True),
    "inactive": ("已停用（學員看不到）", True),
    "unlinked": ("未歸入任何課程", True),
    "narration": ("旁白音檔（掛在教材上）", False),
    "in_use": ("使用中", False),
}


def classify(row: dict, by_id: dict) -> tuple[str, str]:
    meta = row.get("storageMeta") or {}
    if meta.get("mediaKind") in NARRATION_KINDS:
        source_id = str(meta.get("sourceMaterialId") or "")
        source = by_id.get(source_id)
        if not source:
            return "orphan_narration", ""
        return "narration", str(source.get("title") or source.get("filename") or "")
    if row.get("active") is False:
        return "inactive", ""
    if not str(row.get("courseId") or ""):
        return "unlinked", ""
    return "in_use", ""


def inventory(materials: list[dict], backend: str = "") -> dict:
    by_id = {str(item.get("id")): item for item in materials}
    rows = []
    for item in materials:
        item_backend = str(item.get("storageBackend") or "local")
        if backend and item_backend != backend:
            continue
        status, source_title = classify(item, by_id)
        label, attention = STATUS[status]
        rows.append(
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or item.get("filename") or "未命名"),
                "backend": item_backend,
                "status": status,
                "statusLabel": label,
                "needsAttention": attention,
                "sourceTitle": source_title,
                "active": item.get("active") is not False,
                "dateAdded": str(item.get("dateAdded") or item.get("date_added") or ""),
            }
        )
    rows.sort(key=lambda r: (not r["needsAttention"], r["backend"], r["title"]))
    return {
        "rows": rows,
        "total": len(rows),
        "attention": sum(1 for r in rows if r["needsAttention"]),
    }


def register_storage_row_audit(app, *, list_materials=None):
    if app.extensions.get("teacher_storage_row_audit_registered"):
        return app

    def load():
        if list_materials is not None:
            return list_materials()
        from teacher_app.materials import repository

        return repository.list_uploaded_materials(include_inactive=True)

    def view():
        user = getattr(g, "teacher_user", None)
        if not user:
            resolver = getattr(app, "_current_user", None)
            user = resolver() if callable(resolver) else None
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not has_permission(user, "storage.manage"):
            return jsonify({"error": "權限不足：此功能限系統管理者使用。"}), 403
        backend = str(request.args.get("backend") or "").strip().lower()
        return jsonify(inventory(load(), backend))

    app.add_url_rule(
        "/api/admin/storage/rows",
        endpoint="api_admin_storage_rows",
        view_func=view,
        methods=["GET"],
    )
    app.extensions["teacher_storage_row_audit_registered"] = True
    return app
