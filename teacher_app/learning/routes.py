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
import shutil
from pathlib import Path
from typing import Callable

from flask import g, jsonify, request

from teacher_app.auth import rbac_legacy_adapter
from teacher_app.learning import access as learning_access
from teacher_app.learning import content, repository, versioning
from teacher_app.materials import repository as material_repository


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


# Storage providers whose originals live outside the web host.  Production
# materials are stored here (e.g. MEGA), so the web process must fetch a
# temporary copy to read their slide text.
REMOTE_BACKENDS = frozenset({"mega", "gdrive", "oci", "r2"})


def default_source_fetcher(material: dict, paths) -> tuple[Path, Path]:
    """Download a cloud-stored original to a temp folder: ``(temp_root, source)``.

    The caller owns ``temp_root`` and must delete it.  Imported lazily so the AI
    runtime is only loaded when a cloud original really has to be fetched.
    """
    from teacher_app.assessments import ai_runtime

    return ai_runtime.material_source_to_temp(material, paths_provider=lambda: paths)


def _read_rows(extractor, source: Path):
    """Extract slide text from one local file: ``(status, rows, reason, source_kind)``."""
    kind = source.suffix.lower()
    try:
        rows = extractor(source)
    except Exception:
        return "failed", [], "文字抽取失敗", kind
    if rows:
        return "indexed", rows, "", kind
    return "no_text", [], "找不到可擷取文字；掃描型 PDF 不提供假性搜尋結果。", kind


def build_material_index(
    material_id: str,
    material: dict,
    paths,
    *,
    extractor: Callable[[Path], list[tuple[int, str, str]]] = content.extract_slide_text,
    source_fetcher=None,
):
    """Read a material's searchable text, wherever its original is stored.

    Returns ``(status, rows, reason, source_kind)`` and never raises.  ``status``
    is one of ``indexed``, ``no_text``, ``failed`` or ``unsupported``.  Only
    ``indexed``/``no_text`` should replace the stored text; a ``failed`` fetch
    (for example a MEGA timeout) must leave any earlier good index untouched.
    """
    backend = str(material.get("storageBackend") or "").lower()
    if backend == "local":
        path = _material_path(paths, material, material_id)
        if not path.is_file():
            return "unsupported", [], "此教材目前無可安全索引的本機原始檔", backend
        return _read_rows(extractor, path)

    if backend in REMOTE_BACKENDS:
        suffix = Path(str(material.get("filename") or material.get("storageFilename") or "")).suffix.lower()
        if suffix not in content.INDEXABLE_SUFFIXES:
            return "no_text", [], "此檔案類型沒有可搜尋的投影片文字。", suffix or backend
        fetch = source_fetcher or default_source_fetcher
        temp_root = None
        try:
            try:
                temp_root, source = fetch(material, paths)
            except Exception:
                return "failed", [], "無法從雲端儲存取回原始檔，請稍後再試。", backend
            return _read_rows(extractor, Path(source))
        finally:
            if temp_root is not None:
                shutil.rmtree(temp_root, ignore_errors=True)

    return "unsupported", [], "此教材目前無可安全索引的原始檔", backend


def auto_index_material(
    owner,
    material_id: str,
    *,
    extractor: Callable[[Path], list[tuple[int, str, str]]] = content.extract_slide_text,
    paths=None,
    material_getter=None,
    source_fetcher=None,
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

    status, rows, reason, source_kind = build_material_index(
        material_id, material, paths, extractor=extractor, source_fetcher=source_fetcher
    )
    if status not in {"indexed", "no_text"}:
        return terminal(status, reason, source_kind)
    try:
        repository.replace_text_index(
            material_id,
            rows,
            indexed_at=_now(),
            status=status,
            reason=reason,
            source_kind=source_kind,
        )
        return status
    except Exception:
        return terminal("failed", "索引寫入失敗", source_kind)


def register_smart_learning(
    owner,
    *,
    extractor: Callable[[Path], list[tuple[int, str, str]]] = content.extract_slide_text,
    paths=None,
    paths_provider=None,
    material_getter=None,
    source_fetcher=None,
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

    NARRATION_KINDS = {"ai_narration", "teacher_narration"}
    NARRATED_VIEWER_MODES = {"slides", "preview_pdf"}

    def required_narration(user, material):
        """Narration audio the learner must listen to before this slide material counts as done.

        Only a current (not stale after a new version), active narration the learner can open
        is required; anything else leaves the ordinary document rule untouched.
        """
        if str((material or {}).get("viewerMode") or "") not in NARRATED_VIEWER_MODES:
            return None
        source_id = str(material.get("id") or "")
        latest = None
        try:
            rows = material_repository.list_uploaded_materials(include_inactive=False)
        except Exception:
            return None
        for item in rows:
            meta = item.get("storageMeta") or {}
            if meta.get("mediaKind") not in NARRATION_KINDS or str(meta.get("sourceMaterialId") or "") != source_id:
                continue
            if int(meta.get("sourceVersion") or 1) != int(material.get("currentVersion") or 1):
                continue
            if latest is None or str(item.get("dateAdded") or "") > str(latest.get("dateAdded") or ""):
                latest = item
        if latest is None or not learning_access.can_access_learning_item(user, latest):
            return None
        return latest

    def narration_heard(username, audio_id):
        row = repository.get_progress(str(audio_id), username)
        if not row:
            return False
        try:
            watched = json.loads(row.get("watched_buckets") or "[]")
        except Exception:
            watched = []
        if not isinstance(watched, list):
            return False
        return content.media_completion(float(row.get("duration") or 0), watched, 0.9)

    def complete_source_after_narration(user, audio_material):
        """When the narration reaches 90%, finish the slide material if all pages were read."""
        meta = audio_material.get("storageMeta") or {}
        if meta.get("mediaKind") not in NARRATION_KINDS:
            return None
        source_id = str(meta.get("sourceMaterialId") or "")
        source = visible_material(user, source_id) if source_id else None
        if not source or int(meta.get("sourceVersion") or 1) != int(source.get("currentVersion") or 1):
            return None
        username = str(user["username"])
        row = repository.get_progress(source_id, username)
        if not row or not narration_heard(username, audio_material.get("id")):
            return None
        existing = progress_payload(source_id, source, row)
        if existing.get("completed"):
            return None
        position = existing.get("position") or {}
        total = int(position.get("totalPages") or 0)
        document = content.document_completion(total, position.get("visitedPages") or [], 0.9)
        if not document["completed"]:
            return None
        now = _now()
        version = versioning.current_version(source)
        repository.upsert_progress(
            source_id, username, position=position, progress=float(existing.get("progress") or 0),
            completed=True, last_viewed_at=now, completed_at=now,
        )
        repository.set_completed_version(source_id, username, version)
        return source_id

    def progress_payload(material_id, material, data):
        current_version = versioning.current_version(material)
        if not data:
            return {
                "materialId": material_id,
                "position": {},
                "progress": 0,
                "completed": False,
                "lastPositionSeconds": 0,
                "duration": 0,
                "watchedBuckets": [],
                "completionThreshold": 0.9,
                "completedVersion": 0,
                "currentVersion": current_version,
                "requiredCompletionVersion": versioning.required_completion_version(material),
                "retrainingRequired": False,
            }

        raw_completed = bool(data.get("completed", False))
        completed_version = data.get("completed_version", 1)
        version_status = versioning.classify_completion(material, completed_version)
        retraining_required = raw_completed and not version_status["completionCurrent"]

        try:
            position = json.loads(data.get("position", "{}"))
        except Exception:
            position = {}
        if not isinstance(position, dict):
            position = {}

        if retraining_required:
            position = {}
            progress = 0
            last_position = 0
            duration = 0
            watched = []
        else:
            progress = float(data.get("progress", 0) or 0)
            last_position = float(data.get("last_position_seconds", 0) or 0)
            duration = float(data.get("duration", 0) or 0)
            try:
                watched = json.loads(data.get("watched_buckets", "[]"))
            except Exception:
                watched = []
            if not isinstance(watched, list):
                watched = []

        return {
            "materialId": material_id,
            "position": position,
            "progress": max(0, min(100, progress)),
            "completed": raw_completed and version_status["completionCurrent"],
            "lastPositionSeconds": last_position,
            "duration": duration,
            "watchedBuckets": watched,
            "completionThreshold": float(data.get("completion_threshold", 0.9) or 0.9),
            "completedVersion": version_status["completedVersion"] if raw_completed else 0,
            "currentVersion": version_status["currentVersion"],
            "requiredCompletionVersion": version_status["requiredCompletionVersion"],
            "retrainingRequired": retraining_required,
        }

    @app.get("/api/learning-progress")
    def learning_progress_list():
        user, denied = _user(owner)
        if denied:
            return denied
        materials = {
            str(item.get("id") or ""): item
            for item in material_repository.list_uploaded_materials(include_inactive=False)
            if item.get("id") and learning_access.can_access_learning_item(user, item)
        }
        rows = repository.list_progress_for_user(str(user.get("username") or ""))
        items = []
        for row in rows:
            material_id = str(row.get("material_id") or "")
            material = materials.get(material_id)
            if material:
                items.append(progress_payload(material_id, material, row))
        return jsonify({"items": items})

    @app.get("/api/learning-progress/<material_id>")
    def learning_progress_get(material_id):
        user, denied = _user(owner)
        if denied:
            return denied
        material = visible_material(user, material_id)
        if not material:
            return jsonify({"error": "找不到教材"}), 404
        return jsonify(progress_payload(
            material_id,
            material,
            repository.get_progress(material_id, user["username"]),
        ))

    @app.put("/api/learning-progress/<material_id>")
    def learning_progress_put(material_id):
        user, denied = _user(owner)
        if denied:
            return denied
        material = visible_material(user, material_id)
        if not material:
            return jsonify({"error": "找不到教材"}), 404

        body = request.get_json(silent=True) or {}
        requested_position = body.get("position") or {}
        if not isinstance(requested_position, dict):
            return jsonify({"error": "position 格式錯誤"}), 400

        existing = repository.get_progress(material_id, user["username"])
        existing_payload = progress_payload(material_id, material, existing)
        current_version = versioning.current_version(material)
        completion_already_current = bool(existing_payload.get("completed"))
        reset_evidence = bool(existing_payload.get("retrainingRequired"))

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
        narration_pending = False
        media_request = duration > 0 or "watchedBuckets" in body or "lastPositionSeconds" in body
        position = dict(requested_position)

        if media_request:
            position["version"] = current_version
            completed = completion_already_current or content.media_completion(duration, buckets, threshold)
            if duration > 0:
                covered = sum(
                    min(10.0, max(0.0, duration - bucket * 10))
                    for bucket in set(buckets)
                )
                progress = min(100.0, (covered / duration) * 100.0)
            else:
                progress = 0.0
        else:
            try:
                page = int(requested_position.get("page") or 0)
                total_pages = int(requested_position.get("totalPages") or 0)
            except (TypeError, ValueError):
                page = total_pages = 0

            if 1 <= page <= total_pages and total_pages > 0:
                visited = []
                if not reset_evidence and existing:
                    try:
                        prior_position = json.loads(existing.get("position", "{}"))
                    except Exception:
                        prior_position = {}
                    if (
                        isinstance(prior_position, dict)
                        and int(prior_position.get("version") or current_version) == current_version
                    ):
                        prior_visited = prior_position.get("visitedPages") or []
                        if isinstance(prior_visited, list):
                            visited.extend(prior_visited)
                visited.append(page)
                document = content.document_completion(total_pages, visited, threshold)
                position = {
                    "page": page,
                    "totalPages": total_pages,
                    "visitedPages": document["visitedPages"],
                    "version": current_version,
                }
                progress = float(document["progress"])
                narration = required_narration(user, material)
                narration_ok = narration is None or narration_heard(str(user["username"]), narration.get("id"))
                narration_pending = bool(document["completed"]) and not narration_ok
                completed = completion_already_current or (bool(document["completed"]) and narration_ok)
            else:
                try:
                    progress = max(0, min(100, float(body.get("progress", 0))))
                except (TypeError, ValueError):
                    return jsonify({"error": "progress 格式錯誤"}), 400
                position["version"] = current_version
                completed = completion_already_current or bool(body.get("completed", False))

        now = _now()
        repository.upsert_progress(
            material_id,
            user["username"],
            position=position,
            progress=progress,
            completed=completed,
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
        if completed:
            repository.set_completed_version(
                material_id,
                user["username"],
                current_version,
            )
        source_completed = complete_source_after_narration(user, material) if media_request else None

        return jsonify({
            "narrationPending": narration_pending,
            "sourceCompleted": source_completed or "",
            "ok": True,
            "materialId": material_id,
            "position": position,
            "progress": round(float(progress), 2),
            "completed": completed,
            "lastPositionSeconds": last,
            "duration": duration,
            "watchedBuckets": buckets,
            "lastViewedAt": now,
            "completedVersion": current_version if completed else int(existing_payload.get("completedVersion") or 0),
            "currentVersion": current_version,
            "requiredCompletionVersion": versioning.required_completion_version(material),
            "retrainingRequired": bool(reset_evidence and not completed),
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
        status, rows, reason, source_kind = build_material_index(
            material_id,
            material,
            current_paths(),
            extractor=extractor,
            source_fetcher=source_fetcher,
        )
        if status in {"unsupported", "failed"}:
            # A failed fetch/extract keeps any earlier good text rows; only the
            # status is updated.  409 (not 5xx) so proxies pass the JSON body on.
            repository.write_terminal_status(
                material_id,
                status,
                page_count=0,
                indexed_at="" if status == "unsupported" else _now(),
                reason=reason,
                source_kind=source_kind,
            )
            return jsonify({"error": reason, "status": status}), 409
        repository.replace_text_index(
            material_id,
            rows,
            indexed_at=_now(),
            status=status,
            reason=reason,
            source_kind=source_kind,
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
