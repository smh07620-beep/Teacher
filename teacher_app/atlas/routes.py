"""Canonical Atlas HTTP compatibility routes.

Atlas CRUD, row projection, scope, visibility, teaching-resource search, local
image storage and DOCX import orchestration live in ``teacher_app.atlas``.
This root module keeps only the established HTTP/RBAC compatibility surface.
"""
from __future__ import annotations

from typing import Callable

from flask import g, jsonify, request, send_from_directory

from teacher_app.atlas import image_store as atlas_image_store
from teacher_app.atlas import importer as atlas_importer
from teacher_app.atlas import search as atlas_search
from teacher_app.atlas import service as atlas_service
from teacher_app.common.errors import ApiError
from teacher_app.materials import repository as material_repository


ATLAS_CATEGORIES = atlas_service.ATLAS_CATEGORIES


def _error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra or {})
    return jsonify(body), exc.status


def register_atlas_70(
    owner,
    *,
    paths=None,
    paths_provider: Callable[[], object] | None = None,
    material_getter: Callable[[str], dict | None] | None = None,
):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_atlas_70_registered"):
        return app

    if paths is None and paths_provider is None:
        raise ValueError("Atlas routes require canonical StoragePaths or a paths_provider")
    get_material = material_getter or material_repository.get_material

    def current_paths():
        resolved = paths_provider() if paths_provider is not None else paths
        if resolved is None:
            raise RuntimeError("Atlas storage paths are unavailable")
        return resolved

    def user_or_denied():
        user = getattr(g, "teacher_user", None)
        if not user:
            return None, (jsonify({"error": "請先登入。", "loginRequired": True}), 401)
        return user, None

    @app.post("/api/atlas/images")
    def atlas_image_upload():
        user, denied = user_or_denied()
        if denied:
            return denied
        group = str(request.form.get("group") or "").strip()
        if not atlas_service.can_manage(user, group):
            return jsonify({"error": "無權管理此組圖譜。"}), 403
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            return jsonify({"error": "缺少圖片檔案。"}), 400
        raw = uploaded.read()
        try:
            storage = current_paths()
            stored = atlas_image_store.store_image_bytes(
                storage.material_storage,
                raw,
                uploaded.filename,
            )
        except atlas_image_store.AtlasImageError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({
            "imageUrl": stored["imageUrl"],
            "thumbnailUrl": stored["thumbnailUrl"],
        }), 201

    @app.get("/api/atlas/images/<path:name>")
    def atlas_image_read(name):
        user, denied = user_or_denied()
        if denied:
            return denied
        try:
            storage = current_paths()
            directory, safe, image_url = atlas_image_store.requested_image(
                storage.material_storage,
                name,
            )
        except atlas_image_store.AtlasImageError:
            return jsonify({"error": "找不到圖譜圖片。"}), 404
        if not atlas_service.image_visible(user, image_url):
            return jsonify({"error": "找不到圖譜圖片。"}), 404
        return send_from_directory(str(directory), safe)

    @app.post("/api/atlas/import-docx/<material_id>/preview")
    def atlas_docx_preview(material_id):
        user, denied = user_or_denied()
        if denied:
            return denied
        try:
            storage = current_paths()
            payload = atlas_importer.preview_import(
                user,
                material_id,
                storage.uploaded_slides_dir,
                legacy_material_getter=get_material,
            )
        except ApiError as exc:
            return _error(exc)
        return jsonify(payload)

    @app.post("/api/atlas/import-docx/<material_id>/confirm")
    def atlas_docx_confirm(material_id):
        user, denied = user_or_denied()
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            storage = current_paths()
            payload = atlas_importer.confirm_import(
                user,
                material_id,
                body,
                uploaded_slides_dir=storage.uploaded_slides_dir,
                material_storage=storage.material_storage,
                legacy_material_getter=get_material,
            )
        except ApiError as exc:
            return _error(exc)
        return jsonify(payload), 201

    @app.get("/api/atlas")
    def atlas_list():
        user, denied = user_or_denied()
        if denied:
            return denied
        try:
            items = atlas_service.list_items(
                user,
                category=str(request.args.get("category", "")).strip(),
                group_filter=str(request.args.get("group", "")).strip(),
                tag_filter=str(request.args.get("tag", "")),
                status_filter=str(request.args.get("status", "")),
                query=str(request.args.get("q", "")),
            )
        except ApiError as exc:
            return _error(exc)
        return jsonify({"items": items, "categories": sorted(ATLAS_CATEGORIES)})

    @app.get("/api/atlas/<item_id>")
    def atlas_get(item_id):
        user, denied = user_or_denied()
        if denied:
            return denied
        try:
            item = atlas_service.get_item(user, item_id)
        except ApiError as exc:
            return _error(exc)
        return jsonify({
            "item": item,
            "questionContract": {"atlasItemId": item["id"], "status": "not_available"},
        })

    @app.get("/api/teaching-resource-search")
    def teaching_resource_search():
        user, denied = user_or_denied()
        if denied:
            return denied
        try:
            items = atlas_search.search_resources(user, str(request.args.get("q", "")))
        except ApiError as exc:
            return _error(exc)
        return jsonify({"items": items})

    @app.post("/api/atlas")
    def atlas_create():
        user, denied = user_or_denied()
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            item_id = atlas_service.create_item(user, body)
        except ApiError as exc:
            return _error(exc)
        return jsonify({"ok": True, "id": item_id}), 201

    @app.patch("/api/atlas/<item_id>")
    def atlas_update(item_id):
        user, denied = user_or_denied()
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            atlas_service.update_item(user, item_id, body)
        except ApiError as exc:
            return _error(exc)
        return jsonify({"ok": True})

    @app.delete("/api/atlas/<item_id>")
    def atlas_delete(item_id):
        user, denied = user_or_denied()
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            atlas_service.delete_item(
                user,
                item_id,
                confirmed=bool(body.get("confirmed")),
            )
        except ApiError as exc:
            return _error(exc)
        return jsonify({"ok": True})

    app.extensions["teacher_atlas_70_registered"] = True
    return app
