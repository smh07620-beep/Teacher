"""Async orchestration for approved teacher-script local AI narration."""
from __future__ import annotations

import datetime as dt
import logging
import os
import uuid
from typing import Any, Mapping

from teacher_app.common import scope
from teacher_app.materials import media_audio_repository, media_audio_runtime, media_script_repository
from teacher_app.materials import repository as material_repository


LOGGER = logging.getLogger(__name__)


class MediaAudioLimitError(RuntimeError):
    pass


def _env_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(lower, min(upper, value))


def _username(actor: Mapping[str, Any] | None) -> str:
    return str((actor or {}).get("username") or "").strip()[:100]


def _voice(value: Any) -> str:
    voice = str(value or "").strip().lower()
    if voice not in media_audio_runtime.ALLOWED_VOICES:
        voice = media_audio_runtime.public_status().get("defaultVoice") or "zf_xiaoxiao"
    return voice


def _parse_stamp(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def expire_unclaimed_preview(job: Mapping[str, Any] | None) -> dict | None:
    """Turn an abandoned queued preview into a clear retryable failure."""
    current = dict(job or {})
    request_data = current.get("request") or {}
    if current.get("status") != "queued" or not bool(request_data.get("preview")):
        return current or None
    updated = _parse_stamp(current.get("updatedAt") or current.get("createdAt"))
    timeout_seconds = _env_int("MEDIA_AUDIO_PREVIEW_QUEUE_TIMEOUT_SECONDS", 45, 15, 300)
    if updated is None or (dt.datetime.now(dt.timezone.utc) - updated).total_seconds() < timeout_seconds:
        return current
    message = "本機 Kokoro AI Worker 尚未取得試聽工作，已停止等待；請確認 Worker 在線後再試。"
    media_audio_repository.fail_queued_preview(
        str(current.get("id") or ""), str(current.get("updatedAt") or ""), message
    )
    return media_audio_repository.get_job(str(current.get("id") or "")) or current


def prepare_request(data: Mapping[str, Any], actor: Mapping[str, Any] | None) -> dict:
    username = _username(actor)
    if not username:
        raise ValueError("無法確認目前登入帳號")
    script_id = str(data.get("scriptId") or "").strip()[:120]
    if not script_id:
        raise ValueError("請選擇已核准講稿")
    script = media_script_repository.get_script(script_id)
    if not script:
        raise LookupError("找不到指定講稿")
    if str(script.get("draftType") or "script") != "script":
        raise ValueError("只有教學講稿類型可以產生 AI 語音")
    if str(script.get("status") or "") != "approved":
        raise ValueError("只有已核准講稿可以產生 AI 語音")
    # An authoring source may intentionally remain inactive until a teacher
    # publishes it.  Existence + normal scope are the relevant TTS checks here.
    source = material_repository.get_material(str(script.get("materialId") or ""))
    if not source:
        raise LookupError("來源教材已不存在")
    return {
        "id": f"majob-{uuid.uuid4().hex}",
        "script_id": script_id,
        "material_id": str(script.get("materialId") or ""),
        "group_key": str(script.get("group") or source.get("group") or ""),
        "training_area": str(script.get("area") or source.get("area") or ""),
        "actor_username": username,
        "request": {
            "scriptId": script_id,
            "voice": _voice(data.get("voice")),
            "instructions": str(data.get("instructions") or "").strip()[:500],
        },
    }


def prepare_preview_request(data: Mapping[str, Any], actor: Mapping[str, Any] | None) -> dict:
    username = _username(actor)
    if not username:
        raise ValueError("無法確認目前登入帳號")
    actor = actor or {}
    return {
        "id": f"majob-{uuid.uuid4().hex}",
        "script_id": "",
        "material_id": "",
        "group_key": scope.normalize_group(actor.get("preferredGroup")),
        "training_area": scope.normalize_area(actor.get("preferredArea")),
        "actor_username": username,
        "request": {
            "preview": True,
            "voice": _voice(data.get("voice")),
        },
    }


def _enforce_queue_limits(username: str, *, preview: bool = False) -> None:
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat()
    if preview:
        max_actor = _env_int("MEDIA_AUDIO_PREVIEW_MAX_ACTIVE_PER_USER", 3, 1, 10)
        max_total = _env_int("MEDIA_AUDIO_PREVIEW_MAX_ACTIVE_TOTAL", 10, 1, 50)
        max_per_minute = _env_int("MEDIA_AUDIO_PREVIEW_MAX_PER_MINUTE", 10, 1, 30)
        actor_active = media_audio_repository.active_preview_count_for_actor(username)
        total_active = media_audio_repository.total_active_preview_count()
        recent_count = media_audio_repository.recent_preview_count_for_actor(username, since)
        if actor_active >= max_actor:
            raise MediaAudioLimitError("目前已有語音試聽排隊或執行中，請稍候完成後再試")
        if total_active >= max_total:
            raise MediaAudioLimitError("語音試聽佇列目前已滿，請稍後再試")
        if recent_count >= max_per_minute:
            raise MediaAudioLimitError("語音試聽送出過於頻繁，請稍後再試")
        return

    max_actor = _env_int("MEDIA_AUDIO_JOB_MAX_ACTIVE_PER_USER", 1, 1, 5)
    max_total = _env_int("MEDIA_AUDIO_JOB_MAX_ACTIVE_TOTAL", 5, 1, 50)
    max_per_minute = _env_int("MEDIA_AUDIO_JOB_MAX_PER_MINUTE", 2, 1, 20)
    if media_audio_repository.active_formal_count_for_actor(username) >= max_actor:
        raise MediaAudioLimitError("目前已有正式 AI 語音工作排隊或執行中，請完成後再送出")
    if media_audio_repository.total_active_formal_count() >= max_total:
        raise MediaAudioLimitError("正式 AI 語音佇列目前已滿，請稍後再試")
    if media_audio_repository.recent_formal_count_for_actor(username, since) >= max_per_minute:
        raise MediaAudioLimitError("正式 AI 語音送出過於頻繁，請稍後再試")


def enqueue(data: Mapping[str, Any], actor: Mapping[str, Any] | None) -> dict:
    if not media_audio_runtime.configured():
        raise RuntimeError("免費本機 AI 語音尚未啟用；請完成 Cloudflare R2 與本機 Kokoro AI Worker 設定。")
    values = prepare_request(data, actor)
    _enforce_queue_limits(values["actor_username"])
    return media_audio_repository.create_job(values)


def enqueue_preview(data: Mapping[str, Any], actor: Mapping[str, Any] | None) -> dict:
    if not media_audio_runtime.configured():
        raise RuntimeError("免費本機 AI 語音尚未啟用；請完成 Cloudflare R2 與本機 Kokoro AI Worker 設定。")
    values = prepare_preview_request(data, actor)
    stale_minutes = _env_int("MEDIA_AUDIO_PREVIEW_STALE_MINUTES", 8, 3, 120)
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=stale_minutes)).isoformat()
    media_audio_repository.expire_stale_previews(cutoff)

    # Preview clicks are idempotent per user + voice. Reuse the in-flight job
    # instead of creating duplicates that later trip the preview queue limit.
    existing = expire_unclaimed_preview(
        media_audio_repository.active_preview_job_for_actor(
            values["actor_username"],
            str((values.get("request") or {}).get("voice") or ""),
        )
    )
    if existing and str(existing.get("status") or "") in media_audio_repository.ACTIVE_STATUSES:
        existing["_reusedActive"] = True
        return existing
    _enforce_queue_limits(values["actor_username"], preview=True)
    return media_audio_repository.create_job(values)


class MediaAudioJobProcessor:
    def run_job(self, job_id: str) -> bool:
        token = uuid.uuid4().hex
        job = media_audio_repository.claim(job_id, token)
        if not job:
            return False

        def progress(percent, stage, detail):
            media_audio_repository.set_progress(job_id, token, percent, stage, detail)

        try:
            request = job.get("request") or {}
            if bool(request.get("preview")):
                result = media_audio_runtime.generate_voice_preview(
                    job_id=job_id,
                    voice=str(request.get("voice") or ""),
                    progress_callback=progress,
                )
            else:
                script = media_script_repository.get_script(str(job.get("scriptId") or request.get("scriptId") or ""))
                if not script:
                    raise RuntimeError("講稿已不存在")
                if str(script.get("draftType") or "script") != "script" or str(script.get("status") or "") != "approved":
                    raise RuntimeError("AI 語音來源必須是已核准教學講稿")
                source = material_repository.get_material(str(job.get("materialId") or script.get("materialId") or ""))
                if not source:
                    raise RuntimeError("來源教材已不存在")
                result = media_audio_runtime.generate_audio(
                    job_id=job_id,
                    script=script,
                    source=source,
                    voice=str(request.get("voice") or ""),
                    instructions=str(request.get("instructions") or ""),
                    progress_callback=progress,
                )
            media_audio_repository.complete(job_id, token, result)
        except Exception as exc:
            LOGGER.warning(
                "AI media audio job failed job_id=%s error_type=%s",
                str(job_id or "")[:120],
                type(exc).__name__,
            )
            media_audio_repository.fail(job_id, token, str(exc))
        return True

    def run_next_queued(self) -> bool:
        limit = _env_int("MEDIA_AUDIO_JOB_RECOVERY_LIMIT", 10, 1, 50)
        for job in media_audio_repository.list_queued(limit=limit):
            if self.run_job(str(job.get("id") or "")):
                return True
        return False

    def recover_stale(self) -> int:
        minutes = _env_int("MEDIA_AUDIO_JOB_STALE_MINUTES", 30, 5, 240)
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat()
        return media_audio_repository.requeue_stale_processing(cutoff)


def public_job(job: Mapping[str, Any]) -> dict:
    job = expire_unclaimed_preview(job) or job
    status = str(job.get("status") or "queued")
    request_data = job.get("request") or {}
    result = {
        "jobId": job.get("id"),
        "status": status,
        "scriptId": job.get("scriptId"),
        "materialId": job.get("materialId"),
        "preview": bool(request_data.get("preview")),
        "reusedActive": bool(job.get("_reusedActive")),
        "progress": {
            "percent": job.get("progressPercent", 0),
            "stage": job.get("progressStage", ""),
            "detail": job.get("progressDetail", ""),
        },
        "createdAt": job.get("createdAt", ""),
        "updatedAt": job.get("updatedAt", ""),
        "startedAt": job.get("startedAt", ""),
        "completedAt": job.get("completedAt", ""),
    }
    if status == "completed":
        payload = dict(job.get("result") or {})
        if payload.get("preview") and payload.get("previewObjectKey"):
            try:
                payload["previewUrl"] = media_audio_runtime.preview_url(str(payload.get("previewObjectKey") or ""))
            except Exception as exc:
                LOGGER.warning(
                    "AI media audio preview URL failed job_id=%s error_type=%s",
                    str(job.get("id") or "")[:120],
                    type(exc).__name__,
                )
                payload["previewUrl"] = ""
            payload.pop("previewObjectKey", None)
        result["result"] = payload
    elif status == "failed":
        result["error"] = str(job.get("error") or "AI 語音產生失敗")
    return result


__all__ = [
    "MediaAudioJobProcessor",
    "MediaAudioLimitError",
    "enqueue",
    "enqueue_preview",
    "expire_unclaimed_preview",
    "prepare_preview_request",
    "prepare_request",
    "public_job",
]
