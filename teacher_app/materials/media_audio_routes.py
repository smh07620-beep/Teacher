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


_AI_QUEUE_NAMES = {"ai_questions", "media_scripts", "ai_presentations", "ai_videos", "media_audio", "media_subtitles"}


def _is_ai_worker_heartbeat(row: dict, capabilities: dict) -> bool:
    """Recognize current and older dedicated AI Worker heartbeat shapes."""
    kind = str(capabilities.get("workerKind") or "").strip().lower()
    worker_id = str(row.get("worker_id") or row.get("workerId") or "").strip().lower()
    queues = capabilities.get("queues")
    queue_names = {str(item or "").strip() for item in queues} if isinstance(queues, (list, tuple, set)) else set()
    return bool(kind == "ai" or worker_id.endswith("-ai") or queue_names.intersection(_AI_QUEUE_NAMES))


def _kokoro_capability(capabilities: dict) -> bool | None:
    """Read Kokoro readiness from current heartbeat data and compatible legacy keys."""
    kokoro = capabilities.get("kokoro")
    if isinstance(kokoro, dict) and "available" in kokoro:
        return bool(kokoro.get("available"))
    for key in ("kokoroInstalled", "kokoroAvailable", "kokoro_available"):
        if key in capabilities:
            return bool(capabilities.get(key))
    tts = capabilities.get("tts")
    if isinstance(tts, dict):
        nested = tts.get("kokoro")
        if isinstance(nested, dict) and "available" in nested:
            return bool(nested.get("available"))
        for key in ("kokoroInstalled", "kokoroAvailable", "kokoro_available"):
            if key in tts:
                return bool(tts.get(key))
    return None


def _ai_worker_status() -> dict:
    status = {
        "seen": False,
        "online": False,
        "lastSeen": "",
        "heartbeatAgeSeconds": None,
        "workerId": "",
        "queues": [],
        "queueCapabilitiesReported": False,
        "kokoroInstalled": None,
        "diagnosticCode": "worker_not_seen",
        "diagnosticMessage": (
            "尚未收到院內 AI Worker 回報。請確認 Windows 排程「Teacher AI Worker」已啟動，"
            "且 .local-worker.env 的 DATABASE_URL 與 AI Worker dependencies 可用。"
        ),
    }
    try:
        latest = None
        latest_seen = None
        for row in worker_repository.list_heartbeats(100):
            capabilities = row.get("capabilities") or {}
            if not isinstance(capabilities, dict) or not _is_ai_worker_heartbeat(row, capabilities):
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
        heartbeat_age = max(0, int((now - latest_seen).total_seconds()))
        online = heartbeat_age <= 120
        raw_queues = capabilities.get("queues")
        queues = sorted({
            str(item or "").strip()
            for item in raw_queues
            if str(item or "").strip()
        }) if isinstance(raw_queues, (list, tuple, set)) else []
        kokoro_installed = _kokoro_capability(capabilities)

        diagnostic_code = "worker_ready"
        diagnostic_message = "AI Worker 與 Kokoro 已回報，可建立語音試聽。"
        if not online:
            diagnostic_code = "worker_offline"
            diagnostic_message = (
                f"AI Worker 最後回報已超過 120 秒（約 {heartbeat_age} 秒前）。"
                "請檢查 Windows 排程「Teacher AI Worker」是否仍在執行。"
            )
        elif kokoro_installed is False:
            diagnostic_code = "kokoro_unavailable"
            diagnostic_message = (
                "AI Worker 已在線，但 Kokoro capability 回報不可用。"
                "請同步 requirements-ai-worker.txt 後重啟 Teacher AI Worker。"
            )
        elif kokoro_installed is None:
            diagnostic_code = "kokoro_unknown"
            diagnostic_message = (
                "AI Worker 已回報，但沒有 Kokoro capability 資訊。"
                "請更新院內 Worker 程式與 AI dependencies 後重啟。"
            )

        status.update({
            "seen": True,
            "online": online,
            "lastSeen": latest_seen.isoformat(),
            "heartbeatAgeSeconds": heartbeat_age,
            "workerId": str(row.get("worker_id") or row.get("workerId") or "")[:100],
            "queues": queues,
            "queueCapabilitiesReported": isinstance(raw_queues, (list, tuple, set)),
            "kokoroInstalled": kokoro_installed,
            "diagnosticCode": diagnostic_code,
            "diagnosticMessage": diagnostic_message,
        })
    except Exception:
        status.update({
            "statusUnavailable": True,
            "diagnosticCode": "status_unavailable",
            "diagnosticMessage": "Web 無法讀取 AI Worker heartbeat 狀態；請檢查資料庫連線與 worker heartbeat table。",
        })
    return status


def _ai_worker_online_error(worker: dict | None = None, *, required_queue: str = ""):
    """Fail closed unless the dedicated AI Worker reports the required queue."""
    worker = worker or _ai_worker_status()
    if not worker.get("online"):
        return jsonify({
            "error": str(worker.get("diagnosticMessage") or "本機 AI Worker 尚未在線。"),
            "workerOffline": True,
            "worker": worker,
        }), 503
    queue = str(required_queue or "").strip()
    if queue and queue not in set(worker.get("queues") or []):
        return jsonify({
            "error": (
                f"AI Worker 已在線，但尚未回報 {queue} 處理能力。"
                "請更新院內 Teacher AI Worker 至目前 main 並重新啟動。"
            ),
            "workerCapabilityMissing": True,
            "requiredQueue": queue,
            "worker": worker,
        }), 503
    return None


def _worker_ready_error():
    """Fail closed for narration/video work that additionally requires Kokoro."""
    worker = _ai_worker_status()
    online_error = _ai_worker_online_error(worker, required_queue="media_audio")
    if online_error:
        return online_error
    if worker.get("kokoroInstalled") is not True:
        return jsonify({
            "error": str(worker.get("diagnosticMessage") or "Kokoro 語音能力尚未就緒。"),
            "kokoroUnavailable": True,
            "worker": worker,
        }), 503
    return None


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
            and "media_audio" in set(payload["worker"].get("queues") or [])
            and payload["worker"].get("kokoroInstalled") is True
        )
        if payload["readyForPreview"]:
            payload["diagnostic"] = {
                "code": "ready",
                "message": "AI Worker、Kokoro 與 R2 均已就緒，可直接試聽。",
            }
        elif not payload.get("providerReady"):
            payload["diagnostic"] = {
                "code": "provider_not_ready",
                "message": "AI_TTS_PROVIDER 尚未設定為 Kokoro。",
            }
        elif not payload.get("r2Ready"):
            payload["diagnostic"] = {
                "code": "r2_not_ready",
                "message": "Cloudflare R2 尚未完成設定，AI 語音無法保存試聽結果。",
            }
        elif payload["worker"].get("online") and "media_audio" not in set(payload["worker"].get("queues") or []):
            payload["diagnostic"] = {
                "code": "media_audio_capability_missing",
                "message": "AI Worker 已在線，但尚未回報 media_audio queue；請更新院內 Worker 至目前 main 後重啟。",
            }
        else:
            payload["diagnostic"] = {
                "code": str(payload["worker"].get("diagnosticCode") or "worker_not_ready"),
                "message": str(payload["worker"].get("diagnosticMessage") or "AI Worker 尚未就緒。"),
            }
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
        cached = media_audio_runtime.cached_voice_preview(body.get("voice"))
        if cached:
            audit.record_event(
                actor=user,
                action="media.audio.preview",
                target_type="media_audio_voice",
                target_id=str(cached.get("voice") or ""),
                group=str(user.get("preferredGroup") or ""),
                detail={"preview": True, "replayed": True},
            )
            return jsonify({
                "jobId": "",
                "status": "completed",
                "preview": True,
                "result": cached,
            })
        readiness_error = _worker_ready_error()
        if readiness_error:
            return readiness_error
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
        readiness_error = _worker_ready_error()
        if readiness_error:
            return readiness_error
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
