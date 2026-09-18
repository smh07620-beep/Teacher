"""Formal Atlas HTTP compatibility adapter.

Atlas CRUD, row projection, scope, visibility, teaching-resource search and
local image storage live in ``teacher_app.atlas``. This root module keeps the
established URLs plus the legacy DOCX import seam.
"""
from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

from flask import jsonify, request, send_from_directory

from teacher_app.atlas import image_store as atlas_image_store
from teacher_app.atlas import repository as atlas_repository
from teacher_app.atlas import search as atlas_search
from teacher_app.atlas import service as atlas_service
from teacher_app.common.errors import ApiError


ATLAS_CATEGORIES = atlas_service.ATLAS_CATEGORIES
_tags = atlas_service.tags


def _error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra or {})
    return jsonify(body), exc.status


def register_atlas_70(base):
    app = base.app
    if app.extensions.get("teacher_atlas_70_registered"):
        return app

    def user_or_denied():
        user = base._current_user()
        if not user:
            return None, (jsonify({"error": "請先登入。", "loginRequired": True}), 401)
        return user, None

    def docx_source(material_id):
        material = base.get_material(material_id)
        if not material:
            return None, None
        path = (
            Path(base.UPLOADED_SLIDES_DIR)
            / str(material.get("folder") or material_id)
            / str(material.get("storageFilename") or material.get("filename") or "")
        )
        return material, path if path.suffix.lower() == ".docx" and path.is_file() else None

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
            stored = atlas_image_store.store_image_bytes(
                base.MATERIAL_STORAGE,
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
            directory, safe, image_url = atlas_image_store.requested_image(
                base.MATERIAL_STORAGE,
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
        material, path = docx_source(material_id)
        if not material or not path:
            return jsonify({"error": "需要可安全存取的 DOCX 原始檔。"}), 409
        group = material.get("group") or material.get("groupKey")
        if not atlas_service.can_manage(user, group):
            return jsonify({"error": "無權管理此教材。"}), 403
        from smart_learning_67 import preview_docx_atlas

        preview = preview_docx_atlas(path)
        preview["warnings"] = list(preview.get("warnings") or []) + [
            "只會匯入可驗證的內嵌圖片；浮動圖、SmartArt、圖表、群組物件、OLE 與損壞 relationship 不會自動建立圖譜。"
        ]
        return jsonify({
            "materialId": material_id,
            "preview": preview,
            "defaultGroup": group,
            "initialStatus": "draft",
        })

    @app.post("/api/atlas/import-docx/<material_id>/confirm")
    def atlas_docx_confirm(material_id):
        user, denied = user_or_denied()
        if denied:
            return denied
        material, path = docx_source(material_id)
        if not material or not path:
            return jsonify({"error": "需要可安全存取的 DOCX 原始檔。"}), 409
        source_group = str(material.get("group") or material.get("groupKey") or "")
        if not atlas_service.can_manage(user, source_group):
            return jsonify({"error": "無權管理此教材。"}), 403
        body = request.get_json(silent=True) or {}
        selected = body.get("items")
        if not isinstance(selected, list) or not selected:
            return jsonify({"error": "請至少選擇一張圖片。"}), 400
        common = body.get("metadata") or body.get("commonMetadata") or {}
        if not isinstance(common, dict):
            return jsonify({"error": "共用 metadata 格式不正確。"}), 400

        with zipfile.ZipFile(path) as archive:
            media = [name for name in archive.namelist() if name.startswith("word/media/")]
            created = []
            for picked in selected[:30]:
                if not isinstance(picked, dict):
                    continue
                values = {**common, **picked}
                try:
                    index = int(values.get("index", 0)) - 1
                except (TypeError, ValueError):
                    continue
                if index < 0 or index >= len(media):
                    continue
                raw = archive.read(media[index])
                try:
                    stored = atlas_image_store.store_image_bytes(
                        base.MATERIAL_STORAGE,
                        raw,
                        Path(media[index]).suffix,
                        max_bytes=None,
                    )
                except atlas_image_store.AtlasImageError:
                    continue

                group = str(values.get("group") or source_group).strip()
                if not group or not atlas_service.can_manage(user, group):
                    continue
                category = str(values.get("category") or "microscope")
                if category not in ATLAS_CATEGORIES:
                    category = "microscope"
                timestamp = atlas_service.now()
                item_id = uuid.uuid4().hex
                title = str(values.get("title") or Path(media[index]).stem)[:255]
                username = str(user.get("username") or "")
                atlas_repository.insert_item({
                    "id": item_id,
                    "category": category,
                    "group_key": group,
                    "title": title,
                    "image_url": stored["imageUrl"],
                    "description": str(values.get("description") or "")[:6000],
                    "tags": json.dumps(_tags(values.get("tags")), ensure_ascii=False),
                    "differential_points": str(values.get("differentialPoints") or "")[:6000],
                    "teaching_notes": str(values.get("teachingNotes") or "")[:6000],
                    "difficulty": str(values.get("difficulty") or "general")[:40],
                    "published": False,
                    "source": "docx",
                    "source_material_id": material_id,
                    "source_docx": str(material.get("filename") or "")[:255],
                    "sort_order": int(values.get("sortOrder") or 0),
                    "annotation_json": "{}",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "created_by": username,
                    "updated_by": username,
                })
                created.append(item_id)
        if not created:
            return jsonify({
                "error": "沒有可安全匯入的內嵌圖片。",
                "warnings": ["請確認 DOCX 使用支援的 inline JPG/PNG/WEBP 圖片。"],
            }), 409
        return jsonify({"ok": True, "created": created, "status": "draft"}), 201

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
