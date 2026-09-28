"""Async orchestration for approved teacher-script AI narration."""
from __future__ import annotations

import datetime as dt
import os
import uuid
from typing import Any, Mapping

from teacher_app.materials import media_audio_repository, media_audio_runtime, media_script_repository
from teacher_app.materials import repository as material_repository


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
    if str(script.get("status") or "") != "approved":
        raise ValueError("只有已核准講稿可以產生 AI 語音")
    source = material_repository.get_material(str(script.get("materialId") or ""))
    if not source or not source.get("active", True):
        raise LookupError("來源教材已不存在或停用")
    voice = str(data.get("voice") or "").strip().lower()
    if voice not in media_audio_runtime.ALLOWED_VOICES:
        voice = media_audio_runtime.public_status().get("defaultVoice") or "marin"
    return {
        "id": f"majob-{uuid.uuid4().hex}",
        "script_id": script_id,
        "material_id": str(script.get("materialId") or ""),
        "group_key": str(script.get("group") or source.get("group") or ""),
        "training_area": str(script.get("area") or source.get("area") or ""),
        "actor_username": username,
        "request": {
            "scriptId": script_id,
            "voice": voice,
            "instructions": str(data.get("instructions") or "").strip()[:500],
        },
    }


def enqueue(data: Mapping[str, Any], actor: Mapping[str, Any] | None) -> dict:
    if not media_audio_runtime.configured():
        raise RuntimeError("AI 語音尚未啟用；需設定 OPENAI_API_KEY 與 Cloudflare R2。")
    values = prepare_request(data, actor)
    username = values["actor_username"]
    max_actor = _env_int("MEDIA_AUDIO_JOB_MAX_ACTIVE_PER_USER", 1, 1, 5)
    max_total = _env_int("MEDIA_AUDIO_JOB_MAX_ACTIVE_TOTAL", 5, 1, 50)
    max_per_minute = _env_int("MEDIA_AUDIO_JOB_MAX_PER_MINUTE", 2, 1, 10)
    if media_audio_repository.active_count_for_actor(username) >= max_actor:
        raise MediaAudioLimitError("目前已有 AI 語音工作排隊或執行中，請完成後再送出")
    if media_audio_repository.total_active_count() >= max_total:
        raise MediaAudioLimitError("AI 語音佇列目前已滿，請稍後再試")
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat()
    if media_audio_repository.recent_count_for_actor(username, since) >= max_per_minute:
        raise MediaAudioLimitError("AI 語音送出過於頻繁，請稍後再試")
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
            script = media_script_repository.get_script(str(job.get("scriptId") or request.get("scriptId") or ""))
            if not script:
                raise RuntimeError("講稿已不存在")
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
    status = str(job.get("status") or "queued")
    result = {
        "jobId": job.get("id"),
        "status": status,
        "scriptId": job.get("scriptId"),
        "materialId": job.get("materialId"),
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
        result["result"] = job.get("result") or {}
    elif status == "failed":
        result["error"] = str(job.get("error") or "AI 語音產生失敗")
    return result


__all__ = ["MediaAudioJobProcessor", "MediaAudioLimitError", "enqueue", "prepare_request", "public_job"]
