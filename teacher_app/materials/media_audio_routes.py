"""Teacher routes for approved-script AI narration."""
from __future__ import annotations

import datetime as dt

from flask import g, jsonify, request

from teacher_app.common import audit, scope_filter
from teacher_app.materials import media_audio_jobs, media_audio_repository, media_audio_runtime, media_script_repository
from teacher_app.worker import repository as worker_repository


def _actor(owner=None):
    user = getattr(g, "teacher_user", None)
    if user is not None:
        return user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _scope(owner, group: str):
    _user, denied = scope_filter.scoped_groups(owner, "material.manage", {str(group or "").strip()})
    return denied


def _ai_worker_status() -> dict:
    status = {
        "seen": False,
        "online": False,
        "lastSeen": "",
        "workerId": "",
        "kokoroInstalled": None,
    }
    try:
        latest = None
        latest_seen = None
        for row in worker_repository.list_heartbeats(100):
            capabilities = row.get("capabilities") or {}
            if not isinstance(capabilities, dict) or str(capabilities.get("workerKind") or "") != "ai":
                continue
            raw_seen = str(row.get("last_seen") or row.get("lastSeen") or "").strip()
            try:
                seen = dt.datetime.fromisoformat(raw_seen.replace("Z", "+00:00"))
                if seen.tzinfo is None:
                    seen = seen.replace(tzinfo=dt.timezone.utc)
                seen = seen.astimezone(dt.timezone.utc)
            except (TypeError, ValueError):
                continue
            if latest_seen is None or seen > latest_seen:
                latest = (row, capabilities)
                latest_seen = seen
        if latest is None or latest_seen is None:
            return status
        row, capabilities = latest
        now = dt.datetime.now(dt.timezone.utc)
        kokoro = capabilities.get("kokoro") if isinstance(capabilities.get("kokoro"), dict) else {}
        status.update({
            "seen": True,
            "online": latest_seen >= now - dt.timedelta(seconds=120),
            "lastSeen": latest_seen.isoformat(),
            "workerId": str(row.get("worker_id") or row.get("workerId") or "")[:100],
            "kokoroInstalled": bool(kokoro.get("available")),
        })
    except Exception:
        status["statusUnavailable"] = True
    return status


def register_media_audio_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_media_audio_routes_registered"):
        return app

    @app.get("/api/media-audio/status")
    def media_audio_status():
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        denied = scope_filter.require_permission(owner, "material.manage")
        if denied:
            return denied
        payload = media_audio_runtime.public_status()
        payload["worker"] = _ai_worker_status()
        payload["readyForPreview"] = bool(
            payload.get("enabled")
            and payload["worker"].get("online")
            and payload["worker"].get("kokoroInstalled") is True
        )
        active_job = media_audio_repository.active_formal_job_for_actor(str(user.get("username") or ""))
        if active_job:
            payload["activeJob"] = media_audio_jobs.public_job(active_job)
        return jsonify(payload)

    @app.post("/api/media-audio/preview")
    def media_audio_preview():
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        denied = scope_filter.require_permission(owner, "material.manage")
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            job = media_audio_jobs.enqueue_preview(body, user)
        except media_audio_jobs.MediaAudioLimitError as exc:
            return jsonify({"error": str(exc), "rateLimited": True}), 429
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"error": str(exc), "notConfigured": True}), 503
        audit.record_event(
            actor=user,
            action="media.audio.preview",
            target_type="media_audio_voice",
            target_id=str((job.get("request") or {}).get("voice") or ""),
            group=str(job.get("group") or ""),
            detail={"jobId": job.get("id", ""), "preview": True},
        )
        return jsonify(media_audio_jobs.public_job(job)), 202

    @app.post("/api/media-audio/generate")
    def media_audio_generate():
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        body = request.get_json(silent=True) or {}
        script_id = str(body.get("scriptId") or "").strip()
        script = media_script_repository.get_script(script_id) if script_id else None
        if not script:
            return jsonify({"error": "找不到指定講稿。"}), 404
        denied = _scope(owner, str(script.get("group") or ""))
        if denied:
            return denied
        if str(script.get("status") or "") != "approved":
            return jsonify({"error": "只有授課教師已核准的講稿可以產生 AI 語音。"}), 409
        try:
            job = media_audio_jobs.enqueue(body, user)
        except media_audio_jobs.MediaAudioLimitError as exc:
            return jsonify({"error": str(exc), "rateLimited": True}), 429
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"error": str(exc), "notConfigured": True}), 503
        audit.record_event(
            actor=user,
            action="media.audio.generate",
            target_type="media_script",
            target_id=script_id,
            group=str(script.get("group") or ""),
            detail={
                "jobId": job.get("id", ""),
                "voice": (job.get("request") or {}).get("voice", ""),
                "aiGeneratedVoice": True,
                "teacherApprovedBy": script.get("approvedBy", ""),
            },
        )
        return jsonify(media_audio_jobs.public_job(job)), 202

    @app.get("/api/media-audio/jobs/<media_audio_job_id>")
    def media_audio_job(media_audio_job_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        job = media_audio_repository.get_job(str(media_audio_job_id))
        if not job:
            return jsonify({"error": "找不到 AI 語音工作"}), 404
        denied = _scope(owner, str(job.get("group") or ""))
        if denied:
            return denied
        return jsonify(media_audio_jobs.public_job(job))

    app.extensions["teacher_media_audio_routes_registered"] = True
    return app


__all__ = ["register_media_audio_routes"]
