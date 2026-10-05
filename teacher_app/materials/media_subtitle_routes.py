"""HTTP routes for AI subtitle generation, review, approval and playback."""
from __future__ import annotations

from flask import Response, abort, g, jsonify, request

from teacher_app.common import audit, content_audience, scope_filter
from teacher_app.common.auth import has_permission
from teacher_app.materials import media_subtitle_jobs, media_subtitle_repository, media_subtitle_runtime
from teacher_app.materials import repository as material_repository
from teacher_app.materials.media_audio_routes import _ai_worker_online_error


def _actor(owner=None):
    user = getattr(g, "teacher_user", None)
    if user is not None:
        return user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _scope(owner, group: str):
    _user, denied = scope_filter.scoped_groups(owner, "material.manage", {str(group or "").strip()})
    return denied


def _learner_visible(user, material_id: str) -> bool:
    material = material_repository.get_material(material_id)
    if not material:
        return False
    if not material.get("active") and not has_permission(user, "material.manage"):
        return False
    meta = content_audience._material_meta([material_id]).get(material_id)  # same package-internal policy as delivery guard
    return bool(not meta or content_audience.visible_to_user(user, meta))


def _public_subtitle(item: dict | None) -> dict | None:
    if not item:
        return None
    return {
        "id": item.get("id", ""),
        "materialId": item.get("materialId", ""),
        "language": item.get("language", "zh-TW"),
        "label": item.get("label", "字幕"),
        "sourceVersion": item.get("sourceVersion", 1),
        "provider": item.get("provider", ""),
        "model": item.get("model", ""),
        "vttUrl": f"/api/media-subtitles/{item.get('id', '')}.vtt",
        "srtUrl": f"/api/media-subtitles/{item.get('id', '')}.srt",
    }


def register_media_subtitle_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_media_subtitle_routes_registered"):
        return app

    @app.post("/api/media-subtitles/generate")
    def media_subtitle_generate():
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        body = request.get_json(silent=True) or {}
        material_id = str(body.get("materialId") or "").strip()
        material = material_repository.get_material(material_id) if material_id else None
        if not material:
            return jsonify({"error": "找不到指定影音教材。"}), 404
        denied = _scope(owner, str(material.get("group") or ""))
        if denied:
            return denied
        readiness_error = _ai_worker_online_error()
        if readiness_error:
            return readiness_error
        try:
            job = media_subtitle_jobs.enqueue(body, user)
        except media_subtitle_jobs.MediaSubtitleLimitError as exc:
            return jsonify({"error": str(exc), "rateLimited": True}), 429
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        audit.record_event(
            actor=user,
            action="media.subtitle.generate",
            target_type="material",
            target_id=material_id,
            group=str(material.get("group") or ""),
            detail={"jobId": job.get("id", ""), "language": (job.get("request") or {}).get("language", "zh-TW")},
        )
        return jsonify(media_subtitle_jobs.public_job(job)), 202

    @app.get("/api/media-subtitles/jobs/<subtitle_job_id>")
    def media_subtitle_job(subtitle_job_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        job = media_subtitle_repository.get_job(str(subtitle_job_id))
        if not job:
            return jsonify({"error": "找不到 AI 字幕工作"}), 404
        denied = _scope(owner, str(job.get("group") or ""))
        if denied:
            return denied
        return jsonify(media_subtitle_jobs.public_job(job))

    @app.get("/api/media-subtitles")
    def media_subtitle_list():
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        material_id = str(request.args.get("materialId") or "").strip()
        material = material_repository.get_material(material_id) if material_id else None
        if not material:
            return jsonify({"error": "找不到指定影音教材。"}), 404
        denied = _scope(owner, str(material.get("group") or ""))
        if denied:
            return denied
        return jsonify(media_subtitle_repository.list_subtitles(material_id))

    @app.patch("/api/media-subtitles/<subtitle_id>")
    def media_subtitle_update(subtitle_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        subtitle = media_subtitle_repository.get_subtitle(str(subtitle_id))
        if not subtitle:
            return jsonify({"error": "找不到字幕草稿。"}), 404
        denied = _scope(owner, str(subtitle.get("group") or ""))
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        status = str(body.get("status") or subtitle.get("status") or "draft").strip().lower()
        if status not in media_subtitle_repository.SUBTITLE_STATUSES:
            return jsonify({"error": "字幕狀態不合法。"}), 400
        label = str(body.get("label") or subtitle.get("label") or "字幕").strip()[:80] or "字幕"
        try:
            vtt = media_subtitle_runtime.normalize_vtt(body.get("vttText") if "vttText" in body else subtitle.get("vttText", ""))
            srt = media_subtitle_runtime.vtt_to_srt(vtt)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        material = material_repository.get_material(str(subtitle.get("materialId") or ""))
        if not material:
            return jsonify({"error": "字幕來源教材已不存在。"}), 409
        if status == "approved" and int(material.get("currentVersion") or 1) != int(subtitle.get("sourceVersion") or 1):
            return jsonify({"error": "來源教材已有新版，請重新產生字幕後再核准。", "staleSource": True}), 409
        before = {"status": subtitle.get("status", ""), "label": subtitle.get("label", "")}
        updated = media_subtitle_repository.update_subtitle(
            str(subtitle_id),
            vtt_text=vtt,
            srt_text=srt,
            label=label,
            status=status,
            actor_username=str(user.get("username") or ""),
        )
        if not updated:
            return jsonify({"error": "字幕更新失敗。"}), 409
        audit.record_event(
            actor=user,
            action="media.subtitle.approve" if status == "approved" else "media.subtitle.update",
            target_type="media_subtitle",
            target_id=str(subtitle_id),
            group=str(updated.get("group") or ""),
            before=before,
            after={"status": updated.get("status", ""), "label": updated.get("label", "")},
            detail={"materialId": updated.get("materialId", ""), "sourceVersion": updated.get("sourceVersion", 1)},
        )
        return jsonify(updated)

    @app.get("/api/materials/<material_id>/subtitles/approved")
    def media_subtitle_approved(material_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not _learner_visible(user, str(material_id)):
            abort(404)
        material = material_repository.get_material(str(material_id)) or {}
        subtitle = media_subtitle_repository.latest_approved(str(material_id))
        if subtitle and int(subtitle.get("sourceVersion") or 1) != int(material.get("currentVersion") or 1):
            subtitle = None
        return jsonify({"subtitle": _public_subtitle(subtitle)})

    def _approved_payload(subtitle_id: str):
        user = _actor(owner)
        if not user:
            return None, (jsonify({"error": "請先登入。", "loginRequired": True}), 401)
        subtitle = media_subtitle_repository.get_subtitle(str(subtitle_id))
        if not subtitle or str(subtitle.get("status") or "") != "approved":
            return None, None
        material_id = str(subtitle.get("materialId") or "")
        if not _learner_visible(user, material_id):
            return None, None
        material = material_repository.get_material(material_id) or {}
        if int(subtitle.get("sourceVersion") or 1) != int(material.get("currentVersion") or 1):
            return None, None
        return subtitle, None

    @app.get("/api/media-subtitles/<subtitle_id>.vtt")
    def media_subtitle_vtt(subtitle_id):
        subtitle, error = _approved_payload(subtitle_id)
        if error:
            return error
        if not subtitle:
            abort(404)
        response = Response(str(subtitle.get("vttText") or ""), mimetype="text/vtt")
        response.headers["Cache-Control"] = "private, max-age=60"
        response.headers["Content-Disposition"] = f"inline; filename=subtitle-{subtitle_id}.vtt"
        return response

    @app.get("/api/media-subtitles/<subtitle_id>.srt")
    def media_subtitle_srt(subtitle_id):
        subtitle, error = _approved_payload(subtitle_id)
        if error:
            return error
        if not subtitle:
            abort(404)
        response = Response(str(subtitle.get("srtText") or ""), mimetype="application/x-subrip")
        response.headers["Cache-Control"] = "private, max-age=60"
        response.headers["Content-Disposition"] = f"attachment; filename=subtitle-{subtitle_id}.srt"
        return response

    app.extensions["teacher_media_subtitle_routes_registered"] = True
    return app


__all__ = ["register_media_subtitle_routes"]
