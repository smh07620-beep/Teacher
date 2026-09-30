"""Async orchestration for AI-generated teacher-reviewed subtitles."""
from __future__ import annotations

import datetime as dt
import os
import re
import uuid
from typing import Any, Mapping

from teacher_app.materials import media_subtitle_repository, media_subtitle_runtime
from teacher_app.materials import repository as material_repository


class MediaSubtitleLimitError(RuntimeError):
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
    material_id = str(data.get("materialId") or "").strip()[:120]
    if not material_id:
        raise ValueError("請選擇影音教材")
    material = material_repository.get_material(material_id)
    if not material:
        raise LookupError("找不到指定影音教材")
    kind = str(material.get("viewerMode") or "").lower()
    backend = str(material.get("storageBackend") or "").lower()
    if kind not in {"video", "audio"} and backend != "external":
        raise ValueError("AI 字幕只支援影音教材")
    language = str(data.get("language") or "zh-TW").strip()[:32]
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?", language):
        raise ValueError("字幕語言代碼格式不正確")
    label = str(data.get("label") or "繁體中文字幕").strip()[:80] or "繁體中文字幕"
    return {
        "id": f"msubjob-{uuid.uuid4().hex}",
        "material_id": material_id,
        "group_key": str(material.get("group") or ""),
        "training_area": str(material.get("area") or ""),
        "actor_username": username,
        "request": {"materialId": material_id, "language": language, "label": label},
    }


def enqueue(data: Mapping[str, Any], actor: Mapping[str, Any] | None) -> dict:
    values = prepare_request(data, actor)
    username = values["actor_username"]
    max_actor = _env_int("MEDIA_SUBTITLE_JOB_MAX_ACTIVE_PER_USER", 2, 1, 10)
    max_total = _env_int("MEDIA_SUBTITLE_JOB_MAX_ACTIVE_TOTAL", 8, 2, 100)
    max_per_minute = _env_int("MEDIA_SUBTITLE_JOB_MAX_PER_MINUTE", 3, 1, 30)
    if media_subtitle_repository.active_count_for_actor(username) >= max_actor:
        raise MediaSubtitleLimitError(f"目前已有 {max_actor} 個 AI 字幕工作排隊或執行中，請完成後再送出")
    if media_subtitle_repository.total_active_count() >= max_total:
        raise MediaSubtitleLimitError("AI 字幕佇列目前已滿，請稍後再試")
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat()
    if media_subtitle_repository.recent_count_for_actor(username, since) >= max_per_minute:
        raise MediaSubtitleLimitError("AI 字幕送出過於頻繁，請稍後再試")
    return media_subtitle_repository.create_job(values)


def run_generation_sync(snapshot: Mapping[str, Any], *, progress_callback=None) -> dict:
    material_id = str(snapshot.get("materialId") or "")
    material = material_repository.get_material(material_id)
    if not material:
        raise RuntimeError("字幕來源教材已不存在，請重新選擇。")
    return media_subtitle_runtime.generate_subtitle(
        material,
        language=str(snapshot.get("language") or "zh-TW"),
        label=str(snapshot.get("label") or "繁體中文字幕"),
        progress_callback=progress_callback,
    )


class MediaSubtitleJobProcessor:
    def run_job(self, job_id: str) -> bool:
        token = uuid.uuid4().hex
        job = media_subtitle_repository.claim(job_id, token)
        if not job:
            return False

        def progress(percent, stage, detail):
            media_subtitle_repository.set_progress(job_id, token, percent, stage, detail)

        try:
            request_data = job.get("request") or {}
            media_subtitle_repository.set_progress(job_id, token, 2, "準備 AI 字幕", "正在確認影音來源與權限")
            result = run_generation_sync(request_data, progress_callback=progress)
            subtitle = media_subtitle_repository.create_subtitle(
                material_id=str(job.get("materialId") or ""),
                group_key=str(job.get("group") or ""),
                training_area=str(job.get("area") or ""),
                language=str(result.get("language") or "zh-TW"),
                label=str(result.get("label") or "繁體中文字幕"),
                vtt_text=str(result.get("vttText") or ""),
                srt_text=str(result.get("srtText") or ""),
                transcript_text=str(result.get("transcriptText") or ""),
                provider=str(result.get("provider") or ""),
                model=str(result.get("model") or ""),
                fallback_used=bool(result.get("fallbackUsed")),
                source_version=int(result.get("sourceVersion") or 1),
                source_sha256=str(result.get("sourceSha256") or ""),
                source_kind=str(result.get("sourceKind") or ""),
                source_locator=str(result.get("sourceLocator") or ""),
                source_job_id=job_id,
                actor_username=str(job.get("actorUsername") or ""),
            )
            media_subtitle_repository.complete(
                job_id,
                token,
                {
                    "subtitleId": subtitle.get("id", ""),
                    "materialId": subtitle.get("materialId", ""),
                    "language": subtitle.get("language", ""),
                    "label": subtitle.get("label", ""),
                    "provider": subtitle.get("provider", ""),
                    "model": subtitle.get("model", ""),
                    "fallbackUsed": subtitle.get("fallbackUsed", False),
                    "sourceVersion": subtitle.get("sourceVersion", 1),
                    "sourceSha256": subtitle.get("sourceSha256", ""),
                    "status": subtitle.get("status", "draft"),
                },
            )
        except Exception as exc:
            media_subtitle_repository.fail(job_id, token, str(exc))
        return True

    def run_next_queued(self) -> bool:
        limit = _env_int("MEDIA_SUBTITLE_JOB_RECOVERY_LIMIT", 20, 1, 100)
        for job in media_subtitle_repository.list_queued(limit=limit):
            if self.run_job(str(job.get("id") or "")):
                return True
        return False

    def recover_stale(self) -> int:
        minutes = _env_int("MEDIA_SUBTITLE_JOB_STALE_MINUTES", 30, 5, 240)
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat()
        return media_subtitle_repository.requeue_stale_processing(cutoff)


def public_job(job: Mapping[str, Any]) -> dict:
    status = str(job.get("status") or "queued")
    result = {
        "jobId": job.get("id"),
        "status": status,
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
        result["error"] = str(job.get("error") or "AI 字幕產生失敗")
    return result


__all__ = [
    "MediaSubtitleJobProcessor", "MediaSubtitleLimitError", "enqueue", "prepare_request", "public_job", "run_generation_sync",
]
