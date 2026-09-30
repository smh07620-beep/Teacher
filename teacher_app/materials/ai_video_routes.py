"""Teacher review APIs for the Phase 1 AI presentation-video pipeline."""
from __future__ import annotations

from flask import Response, abort, g, jsonify, request, send_file

from teacher_app.common import audit, scope_filter
from teacher_app.common.auth import has_role
from teacher_app.materials import ai_presentation_repository as presentation_repository
from teacher_app.materials import ai_video_jobs, ai_video_repository as repository
from teacher_app.materials.ai_video_storage import VideoStorage

_TEACHER_ROLES = {"clinical_teacher", "group_leader"}
_OPERATE_ROLES = _TEACHER_ROLES | {"education_admin", "system_admin"}
_SHARED_BACKENDS = {"r2", "oci", "gdrive", "mega"}


def _actor(owner=None):
    user = getattr(g, "teacher_user", None)
    if user is not None: return user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _scope(owner, group: str):
    _user, denied = scope_filter.scoped_groups(owner, "material.manage", {str(group or "").strip()})
    return denied


def _video_allowed(user, permission: str) -> bool:
    roles = _TEACHER_ROLES if permission == "video.approve" else _OPERATE_ROLES
    return bool(user and any(has_role(user, role) for role in roles))


def _artifact_ready(item: dict) -> bool:
    return bool(item and str(item.get("artifactBackend") or "").lower() in _SHARED_BACKENDS and item.get("artifactStorageKey") and len(str(item.get("artifactSha256") or "")) == 64 and int(item.get("artifactBytes") or 0) > 0 and item.get("artifactMimeType") == repository.MP4_MIME and float(item.get("durationSeconds") or 0) > 0)


def _public_video(item: dict) -> dict:
    keys = ("id", "videoFamilyId", "parentRevisionId", "revisionNumber", "presentationId", "presentationFamilyId", "presentationRevision", "presentationSha256", "group", "area", "title", "status", "artifactSha256", "artifactBytes", "artifactMimeType", "durationSeconds", "timeline", "ttsProvider", "ttsModel", "ttsVoice", "sourceJobId", "createdBy", "updatedBy", "approvedBy", "approvedAt", "publishedAt", "createdAt", "updatedAt")
    result = {key: item.get(key) for key in keys}
    result["previewUrl"] = f"/api/ai-videos/{item.get('id', '')}/preview" if _artifact_ready(item) else ""
    result["vttUrl"] = f"/api/ai-videos/{item.get('id', '')}.vtt" if item.get("vttText") else ""
    result["srtUrl"] = f"/api/ai-videos/{item.get('id', '')}.srt" if item.get("srtText") else ""
    return result


def register_ai_video_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_ai_video_routes_registered"): return app

    @app.get("/api/ai-videos/status")
    def video_status():
        user = _actor(owner)
        if not user: return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not _video_allowed(user, "video.create"): return jsonify({"error": "目前角色不可建立 AI 影片。"}), 403
        return jsonify({"storage": VideoStorage().capability(), "workerRequired": True, "requiresApprovedPresentation": True, "capabilities": {name: _video_allowed(user, name) for name in ("video.create", "video.approve", "video.publish")}})

    @app.post("/api/ai-videos/generate")
    def video_generate():
        user = _actor(owner)
        if not user: return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not _video_allowed(user, "video.create"): return jsonify({"error": "目前角色不可建立 AI 影片。"}), 403
        body = request.get_json(silent=True) or {}; presentation = presentation_repository.get_presentation(str(body.get("presentationId") or ""))
        if not presentation: return jsonify({"error": "找不到 PowerPoint revision。"}), 404
        denied = _scope(owner, str(presentation.get("group") or ""))
        if denied: return denied
        if str(presentation.get("status") or "") not in {"approved", "published"}: return jsonify({"error": "AI 影片來源必須是已由授課教師核准的 PowerPoint revision。"}), 409
        if not presentation.get("artifactStorageKey") or len(str(presentation.get("artifactSha256") or "")) != 64: return jsonify({"error": "PowerPoint durable artifact metadata 不完整。"}), 409
        try: job = ai_video_jobs.enqueue(body, user, presentation)
        except ai_video_jobs.AiVideoLimitError as exc: return jsonify({"error": str(exc), "rateLimited": True}), 429
        except (ValueError, RuntimeError) as exc: return jsonify({"error": str(exc), "notConfigured": True}), 503
        audit.record_event(actor=user, action="video.generate", target_type="ai_presentation", target_id=str(presentation.get("id") or ""), group=str(presentation.get("group") or ""), detail={"jobId": job.get("id"), "presentationRevision": presentation.get("revisionNumber"), "renderedInWeb": False})
        return jsonify(ai_video_jobs.public_job(job)), 202

    @app.get("/api/ai-videos/jobs/<job_id>")
    def video_job(job_id):
        user = _actor(owner)
        if not user: return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        job = repository.get_job(str(job_id))
        if not job: return jsonify({"error": "找不到 AI 影片工作。"}), 404
        denied = _scope(owner, str(job.get("group") or ""))
        return denied if denied else jsonify(ai_video_jobs.public_job(job))

    @app.get("/api/ai-presentations/<presentation_id>/videos")
    def presentation_videos(presentation_id):
        user = _actor(owner)
        if not user: return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        presentation = presentation_repository.get_presentation(str(presentation_id))
        if not presentation: return jsonify({"error": "找不到 PowerPoint revision。"}), 404
        denied = _scope(owner, str(presentation.get("group") or ""))
        return denied if denied else jsonify({"videos": [_public_video(item) for item in repository.list_videos(str(presentation_id))]})

    @app.get("/api/ai-videos/<video_id>/preview")
    def video_preview(video_id):
        user = _actor(owner)
        if not user: return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        video = repository.get_video(str(video_id))
        if not video: abort(404)
        denied = _scope(owner, str(video.get("group") or ""))
        if denied: return denied
        if not _artifact_ready(video): return jsonify({"error": "AI 影片 artifact 尚未完成。"}), 409
        try: response = VideoStorage().browser_response(video, download_name=f"{video.get('title') or 'AI教學影片'}-r{video.get('revisionNumber') or 1}.mp4")
        except RuntimeError as exc: return jsonify({"error": str(exc)}), 503
        return send_file(response, mimetype=repository.MP4_MIME, as_attachment=False, download_name=response.name) if hasattr(response, "name") else response

    def _caption(video_id: str, suffix: str):
        user = _actor(owner)
        if not user: return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        video = repository.get_video(str(video_id))
        if not video: abort(404)
        denied = _scope(owner, str(video.get("group") or ""))
        if denied: return denied
        text = str(video.get("vttText" if suffix == "vtt" else "srtText") or "")
        if not text: abort(404)
        return Response(text, mimetype="text/vtt" if suffix == "vtt" else "application/x-subrip")

    @app.get("/api/ai-videos/<video_id>.vtt")
    def video_vtt(video_id): return _caption(video_id, "vtt")

    @app.get("/api/ai-videos/<video_id>.srt")
    def video_srt(video_id): return _caption(video_id, "srt")

    @app.post("/api/ai-videos/<video_id>/approve")
    def video_approve(video_id):
        user = _actor(owner)
        if not user: return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not _video_allowed(user, "video.approve"): return jsonify({"error": "只有臨床教師或組長可核准 AI 影片。"}), 403
        video = repository.get_video(str(video_id))
        if not video: return jsonify({"error": "找不到 AI 影片。"}), 404
        denied = _scope(owner, str(video.get("group") or ""))
        if denied: return denied
        if not _artifact_ready(video): return jsonify({"error": "AI 影片 artifact durable metadata 不完整。"}), 409
        try: updated = repository.set_status(str(video_id), status="approved", actor_username=str(user.get("username") or ""))
        except ValueError as exc: return jsonify({"error": str(exc)}), 409
        audit.record_event(actor=user, action="video.approve", target_type="ai_presentation_video", target_id=str(video_id), group=str(video.get("group") or ""), after={"status": "approved", "artifactSha256": video.get("artifactSha256")})
        return jsonify({"ok": True, "video": _public_video(updated or {})})

    @app.post("/api/ai-videos/<video_id>/publish")
    def video_publish(video_id):
        user = _actor(owner)
        if not user: return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not _video_allowed(user, "video.publish"): return jsonify({"error": "目前角色不可發布 AI 影片。"}), 403
        video = repository.get_video(str(video_id))
        if not video: return jsonify({"error": "找不到 AI 影片。"}), 404
        denied = _scope(owner, str(video.get("group") or ""))
        if denied: return denied
        if str(video.get("status") or "") not in {"approved", "published"} or not _artifact_ready(video): return jsonify({"error": "AI 影片必須先由授課教師核准且具完整 durable artifact。"}), 409
        receipt = repository.create_publication(video_id=str(video_id), actor_username=str(user.get("username") or ""), receipt={"videoId": video.get("id"), "videoRevision": video.get("revisionNumber"), "presentationId": video.get("presentationId"), "presentationRevision": video.get("presentationRevision"), "artifactBackend": video.get("artifactBackend"), "artifactStorageKey": video.get("artifactStorageKey"), "artifactSha256": video.get("artifactSha256"), "artifactBytes": video.get("artifactBytes"), "artifactMimeType": video.get("artifactMimeType"), "durationSeconds": video.get("durationSeconds")})
        updated = repository.set_status(str(video_id), status="published", actor_username=str(user.get("username") or ""))
        audit.record_event(actor=user, action="video.publish", target_type="ai_presentation_video", target_id=str(video_id), group=str(video.get("group") or ""), after={"status": "published", "receiptKey": receipt.get("receiptKey")})
        return jsonify({"ok": True, "video": _public_video(updated or {}), "publicationReceipt": receipt})

    app.extensions["teacher_ai_video_routes_registered"] = True
    return app


__all__ = ["register_ai_video_routes", "_artifact_ready", "_video_allowed"]
