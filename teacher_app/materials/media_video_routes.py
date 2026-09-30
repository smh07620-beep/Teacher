"""HTTP routes for reviewed teaching-video composition and approval."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common import audit, scope_filter
from teacher_app.materials import media_video_jobs, media_video_repository, media_video_runtime

_APPROVER_ROLES = {"clinical_teacher", "group_leader"}


def _actor(owner=None):
    user = getattr(g, "teacher_user", None)
    if user is not None: return user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _scope(owner, group: str):
    _user, denied = scope_filter.scoped_groups(owner, "material.manage", {str(group or "").strip()})
    return denied


def _can_approve(user: dict | None) -> bool:
    if not user: return False
    roles = {str(user.get("role") or "").strip()}
    roles.update(str(value or "").strip() for value in (user.get("roles") or []))
    return bool(roles & _APPROVER_ROLES)


def _public_video(item: dict, *, include_preview: bool = False) -> dict:
    result = {
        "id": item.get("id", ""), "title": item.get("title", ""), "status": item.get("status", "draft"),
        "presentationId": item.get("presentationId", ""), "narrationMaterialId": item.get("narrationMaterialId", ""),
        "subtitleId": item.get("subtitleId", ""), "group": item.get("group", ""), "area": item.get("area", ""),
        "artifactSha256": item.get("artifactSha256", ""), "artifactBytes": item.get("artifactBytes", 0),
        "durationSeconds": item.get("durationSeconds", 0), "createdBy": item.get("createdBy", ""),
        "approvedBy": item.get("approvedBy", ""), "createdAt": item.get("createdAt", ""),
        "updatedAt": item.get("updatedAt", ""), "approvedAt": item.get("approvedAt", ""),
    }
    if include_preview:
        try: result["previewUrl"] = media_video_runtime.preview_url(item)
        except Exception: result["previewUrl"] = ""
    return result


def register_media_video_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_media_video_routes_registered"): return app

    @app.get("/api/media-videos/status")
    def media_video_status():
        user = _actor(owner)
        if not user: return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        return jsonify(media_video_runtime.public_status())

    @app.post("/api/media-videos/generate")
    def media_video_generate():
        user = _actor(owner)
        if not user: return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        body = request.get_json(silent=True) or {}
        # Prepare first so group is resolved from the exact approved presentation.
        try:
            prepared = media_video_jobs.prepare_request(body, user)
        except LookupError as exc: return jsonify({"error": str(exc)}), 404
        except ValueError as exc: return jsonify({"error": str(exc)}), 400
        denied = _scope(owner, prepared["group_key"])
        if denied: return denied
        try:
            job = media_video_jobs.enqueue(body, user)
        except media_video_jobs.MediaVideoLimitError as exc:
            return jsonify({"error": str(exc), "rateLimited": True}), 429
        except RuntimeError as exc: return jsonify({"error": str(exc)}), 503
        except LookupError as exc: return jsonify({"error": str(exc)}), 404
        except ValueError as exc: return jsonify({"error": str(exc)}), 400
        audit.record_event(actor=user, action="media.video.generate", target_type="ai_presentation",
                           target_id=str(prepared["presentation_id"]), group=prepared["group_key"],
                           detail={"jobId": job.get("id", ""), "narrationMaterialId": prepared["narration_material_id"], "subtitleId": prepared["subtitle_id"]})
        return jsonify(media_video_jobs.public_job(job)), 202

    @app.get("/api/media-videos/jobs/<job_id>")
    def media_video_job(job_id):
        user = _actor(owner)
        if not user: return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        job = media_video_repository.get_job(str(job_id))
        if not job: return jsonify({"error": "找不到影片合成工作"}), 404
        denied = _scope(owner, str(job.get("group") or ""))
        if denied: return denied
        return jsonify(media_video_jobs.public_job(job))

    @app.get("/api/media-videos/<video_id>")
    def media_video_detail(video_id):
        user = _actor(owner)
        if not user: return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        video = media_video_repository.get_video(str(video_id))
        if not video: return jsonify({"error": "找不到影片草稿"}), 404
        denied = _scope(owner, str(video.get("group") or ""))
        if denied: return denied
        return jsonify(_public_video(video, include_preview=True))

    @app.post("/api/media-videos/<video_id>/approve")
    def media_video_approve(video_id):
        user = _actor(owner)
        if not user: return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        video = media_video_repository.get_video(str(video_id))
        if not video: return jsonify({"error": "找不到影片草稿"}), 404
        denied = _scope(owner, str(video.get("group") or ""))
        if denied: return denied
        if not _can_approve(user): return jsonify({"error": "只有臨床教師或組長可以核准教學影片。"}), 403
        if video.get("status") == "approved": return jsonify(_public_video(video, include_preview=True))
        # Fail closed if an input changed after the Worker produced the MP4.
        from teacher_app.materials import ai_presentation_repository, media_subtitle_repository
        from teacher_app.materials import repository as material_repository
        presentation = ai_presentation_repository.get_presentation(str(video.get("presentationId") or ""))
        narration = material_repository.get_material(str(video.get("narrationMaterialId") or ""))
        subtitle = media_subtitle_repository.get_subtitle(str(video.get("subtitleId") or "")) if video.get("subtitleId") else None
        stale = (
            not presentation or presentation.get("status") != "approved"
            or presentation.get("artifactSha256") != video.get("sourcePresentationSha256")
            or not narration or narration.get("storageKey") != video.get("sourceAudioKey")
            or int(narration.get("currentVersion") or 1) != int(video.get("sourceAudioVersion") or 1)
            or (subtitle is not None and (subtitle.get("status") != "approved" or subtitle.get("updatedAt") != video.get("sourceSubtitleUpdatedAt")))
            or (video.get("subtitleId") and subtitle is None)
        )
        if stale: return jsonify({"error": "影片來源已變更，請重新產生影片後再核准。", "staleSource": True}), 409
        updated = media_video_repository.approve_video(str(video_id), str(user.get("username") or ""))
        if not updated: return jsonify({"error": "影片核准失敗"}), 409
        audit.record_event(actor=user, action="media.video.approve", target_type="media_video", target_id=str(video_id),
                           group=str(updated.get("group") or ""), before={"status": video.get("status", "")},
                           after={"status": updated.get("status", "")}, detail={"presentationId": updated.get("presentationId", ""), "artifactSha256": updated.get("artifactSha256", "")})
        return jsonify(_public_video(updated, include_preview=True))

    app.extensions["teacher_media_video_routes_registered"] = True
    return app


__all__ = ["register_media_video_routes"]
