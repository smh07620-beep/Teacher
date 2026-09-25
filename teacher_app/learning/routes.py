"""Canonical smart-learning HTTP and indexing orchestration.

The legacy ``smart_learning_67`` module remains a compatibility import surface,
but route behavior and learning/search persistence live under ``teacher_app``.
Production source-file lookup receives canonical ``StoragePaths`` from the
application factory; owner-shaped path fallbacks remain only for isolated
compatibility fixtures.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Callable

from flask import g, jsonify, request

from teacher_app.auth import rbac_legacy_adapter
from teacher_app.learning import access as learning_access
from teacher_app.learning import content, repository
from teacher_app.materials import repository as material_repository
from teacher_app.materials import versioning as material_versioning


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _user(owner=None):
    user = getattr(g, "teacher_user", None)
    if user is None:
        resolver = getattr(owner, "_current_user", None)
        if callable(resolver):
            user = resolver()
    if not user:
        return None, (jsonify({"error": "請先登入。", "loginRequired": True}), 401)
    return user, None


def _material_path(paths, material: dict, material_id: str) -> Path:
    return (
        Path(paths.uploaded_slides_dir)
        / str(material.get("folder") or material_id)
        / str(material.get("storageFilename") or material.get("filename") or "")
    )


def auto_index_material(
    owner,
    material_id: str,
    *,
    extractor: Callable[[Path], list[tuple[int, str, str]]] = content.extract_slide_text,
    paths=None,
    material_getter=None,
) -> str:
    """Best-effort completion hook; never affects Worker completion/heartbeat."""
    getter = material_getter or getattr(owner, "get_material", None) or material_repository.get_material
    if paths is None:
        app = getattr(owner, "app", owner)
        paths = getattr(app, "config", {}).get("STORAGE_PATHS")
    if paths is None:
        uploaded = getattr(owner, "UPLOADED_SLIDES_DIR", None)
        if uploaded is None:
            raise RuntimeError("StoragePaths is required for material indexing")
        paths = type("IndexPaths", (), {"uploaded_slides_dir": Path(uploaded)})()
    material = getter(material_id)

    def terminal(status: str, reason: str, source_kind: str = "") -> str:
        repository.write_terminal_status(
            material_id,
            status,
            page_count=0,
            indexed_at=_now(),
            reason=reason,
            source_kind=source_kind,
        )
        return status

    if not material:
        return terminal("unsupported", "找不到教材")

    path = _material_path(paths, material, material_id)
    backend = str(material.get("storageBackend") or "")
    if backend != "local" or not path.is_file():
        return terminal("unsupported", "此教材目前無可安全索引的本機原始檔", backend)

    try:
        rows = extractor(path)
    except Exception:
        return terminal("failed", "文字抽取失敗", path.suffix.lower())

    status = "indexed" if rows else "no_text"
    reason = "" if rows else "無可搜尋文字"
    try:
        repository.replace_text_index(
            material_id,
            rows,
            indexed_at=_now(),
            status=status,
            reason=reason,
            source_kind=path.suffix.lower(),
        )
        return status
    except Exception:
        return terminal("failed", "索引寫入失敗", path.suffix.lower())


def register_smart_learning(
    owner,
    *,
    extractor: Callable[[Path], list[tuple[int, str, str]]] = content.extract_slide_text,
    paths=None,
    paths_provider=None,
    material_getter=None,
):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_smart_learning_67_registered"):
        return app
    paths = paths or app.config.get("STORAGE_PATHS")
    if paths is None and paths_provider is None:
        uploaded = getattr(owner, "UPLOADED_SLIDES_DIR", None)
        if uploaded is None:
            raise RuntimeError("StoragePaths is required for smart-learning routes")
        paths = type("LearningPaths", (), {"uploaded_slides_dir": Path(uploaded)})()
    get_material = material_getter or getattr(owner, "get_material", None) or material_repository.get_material

    def current_paths():
        return paths_provider() if paths_provider is not None else paths

    def visible_material(user, material_id):
        material = get_material(material_id)
        if (
            not material
            or not material.get("active", True)
            or not learning_access.can_access_learning_item(user, material)
        ):
            return None
        return material

    @app.get("/api/learning-progress/<material_id>")
    def learning_progress_get(material_id):
        user, denied = _user(owner)
        if denied:
            return denied
        material = visible_material(user, material_id)
        if not material:
            return jsonify({"error": "找不到教材"}), 404
        data = repository.get_progress(material_id, user["username"])
        if not data:
            return jsonify({
                "materialId": material_id,
                "position": {},
                "progress": 0,
                "completed": False,
                "completedVersion": 0,
                "requiredCompletionVersion": int(material.get("requiredCompletionVersion") or 1),
                "lastPositionSeconds": 0,
                "duration": 0,
                "watchedBuckets": [],
                "completionThreshold": 0.9,
            })
        try:
            data["position"] = json.loads(data.get("position", "{}"))
        except Exception:
            data["position"] = {}
        data["materialId"] = data.pop("material_id")
        data.pop("username", None)
        completed_version = int(data.pop("completed_version", 1) or 1)
        current_completion = material_versioning.completion_is_current(material, completed_version)
        data["completed"] = bool(data.get("completed")) and current_completion
        data["completedVersion"] = completed_version
        data["requiredCompletionVersion"] = int(material.get("requiredCompletionVersion") or 1)
        try:
            data["watchedBuckets"] = json.loads(data.pop("watched_buckets", "[]"))
        except Exception:
            data["watchedBuckets"] = []
        data["lastPositionSeconds"] = data.pop("last_position_seconds", 0)
        data["completionThreshold"] = data.pop("completion_threshold", 0.9)
        return jsonify(data)

    @app.put("/api/learning-progress/<material_id>")
    def learning_progress_put(material_id):
        user, denied = _user(owner)
        if denied:
            return denied
        material = visible_material(user, material_id)
        if not material:
            return jsonify({"error": "找不到教材"}), 404

        body = request.get_json(silent=True) or {}
        position = body.get("position") or {}
        if not isinstance(position, dict):
            return jsonify({"error": "position 格式錯誤"}), 400
        try:
            progress = max(0, min(100, float(body.get("progress", 0))))
        except (TypeError, ValueError):
            return jsonify({"error": "progress 格式錯誤"}), 400
        try:
            duration = max(0.0, float(body.get("duration", 0) or 0))
            last = max(0.0, min(duration, float(body.get("lastPositionSeconds", 0) or 0)))
        except (TypeError, ValueError):
            return jsonify({"error": "media progress 格式錯誤"}), 400

        buckets = body.get("watchedBuckets", [])
        if not isinstance(buckets, list):
            return jsonify({"error": "watchedBuckets 格式錯誤"}), 400
        try:
            buckets = sorted({max(0, min(99999, int(item))) for item in buckets})[:10000]
        except (TypeError, ValueError):
            return jsonify({"error": "watchedBuckets 格式錯誤"}), 400

        threshold = 0.9
        media_request = duration > 0 or "watchedBuckets" in body or "lastPositionSeconds" in body
        completed = content.resolved_completion(
            duration,
            buckets,
            body.get("completed", False),
            media_request,
            threshold,
        )
        now = _now()
        current_version = max(1, int(material.get("currentVersion") or 1))
        repository.upsert_progress(
            material_id,
            user["username"],
            position=position,
            progress=progress,
            completed=completed,
            completed_version=current_version,
            last_viewed_at=now,
            completed_at=now if completed else "",
        )
        repository.update_media_progress(
            material_id,
            user["username"],
            last_position_seconds=last,
            duration=duration,
            watched_buckets=buckets,
            completion_threshold=threshold,
            updated_at=now,
        )
        return jsonify({
            "ok": True,
            "materialId": material_id,
            "position": position,
            "progress": progress,
            "completed": completed,
            "completedVersion": current_version if completed else 0,
            "requiredCompletionVersion": int(material.get("requiredCompletionVersion") or 1),
            "lastPositionSeconds": last,
            "duration": duration,
            "watchedBuckets": buckets,
            "lastViewedAt": now,
        })

    @app.get("/api/material-search")
    def material_search():
        user, denied = _user(owner)
        if denied:
            return denied
        query = str(request.args.get("q", "")).strip()[:200]
        material_id = str(request.args.get("materialId", "")).strip()[:100]
        if not query or not material_id:
            return jsonify([])
        material = visible_material(user, material_id)
        if not material:
            return jsonify([])
        rows = repository.search_material(material_id, query, limit=50)
        return jsonify([
            {
                "page": int(row.get("page_no", 0)),
                "title": row.get("title", ""),
                "excerpt": row.get("text", "")[:240],
            }
            for row in rows
        ])

    @app.post("/api/material-search/<material_id>/index")
    def material_index(material_id):
        denied = rbac_legacy_adapter.legacy_admin_guard(app)
        if denied:
            return denied
        material = get_material(material_id)
        if not material:
            return jsonify({"error": "找不到教材"}), 404
        path = _material_path(current_paths(), material, material_id)
        backend = str(material.get("storageBackend") or "")
        if backend != "local" or not path.is_file():
            repository.write_terminal_status(
                material_id,
                "unsupported",
                page_count=0,
                indexed_at="",
                reason="此教材目前無可安全索引的本機原始檔",
                source_kind=backend,
            )
            return jsonify({"error": "此教材目前無可安全索引的本機原始檔", "status": "unsupported"}), 409
        rows = extractor(path)
        status = "indexed" if rows else "no_text"
        reason = "" if rows else "找不到可擷取文字；掃描型 PDF 不提供假性搜尋結果。"
        repository.replace_text_index(
            material_id,
            rows,
            indexed_at=_now(),
            status=status,
            reason=reason,
            source_kind=path.suffix.lower(),
        )
        return jsonify({"ok": True, "pages": len(rows), "searchable": bool(rows), "status": status})

    @app.get("/api/material-search/<material_id>/status")
    def material_index_status(material_id):
        user, denied = _user(owner)
        if denied:
            return denied
        if not visible_material(user, material_id):
            return jsonify({"error": "找不到教材"}), 404
        status = repository.get_index_status(material_id)
        return jsonify(status or {
            "status": "not_indexed",
            "page_count": 0,
            "last_indexed_at": "",
            "failure_reason": "",
            "source_kind": "",
        })

    app.extensions["teacher_smart_learning_67_registered"] = True
    return app


__all__ = ["auto_index_material", "register_smart_learning"]
