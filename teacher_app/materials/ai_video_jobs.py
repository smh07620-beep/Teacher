"""Queue limits, heartbeat recovery, and worker orchestration for AI video Phase 1."""
from __future__ import annotations

import datetime as dt
import os
import uuid
from typing import Any, Mapping

from teacher_app.materials import ai_video_repository as repository
from teacher_app.materials import ai_video_runtime
from teacher_app.materials.ai_video_storage import VideoStorage


class AiVideoLimitError(RuntimeError):
    pass


def _env_int(name: str, default: int, lower: int, upper: int) -> int:
    try: value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError): value = default
    return max(lower, min(upper, value))


def prepare_request(data: Mapping[str, Any], actor: Mapping[str, Any] | None, presentation: Mapping[str, Any]) -> dict:
    username = str((actor or {}).get("username") or "").strip()[:100]
    if not username: raise ValueError("無法確認目前登入帳號。")
    request = {"voice": str(data.get("voice") or "").strip().lower()[:80], "language": "zh-TW"}
    return {"presentation": presentation, "actor_username": username, "request": request}


def _enforce_limits(username: str) -> None:
    if repository.active_count_for_actor(username) >= _env_int("AI_VIDEO_JOB_MAX_ACTIVE_PER_USER", 1, 1, 5): raise AiVideoLimitError("目前已有 AI 影片工作排隊或執行中。")
    if repository.total_active_count() >= _env_int("AI_VIDEO_JOB_MAX_ACTIVE_TOTAL", 3, 1, 20): raise AiVideoLimitError("AI 影片佇列目前已滿，請稍後再試。")
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat()
    if repository.recent_count_for_actor(username, since) >= _env_int("AI_VIDEO_JOB_MAX_PER_MINUTE", 1, 1, 10): raise AiVideoLimitError("AI 影片送出過於頻繁，請稍後再試。")


def enqueue(data: Mapping[str, Any], actor: Mapping[str, Any] | None, presentation: Mapping[str, Any]) -> dict:
    if not VideoStorage().capability().get("available"): raise RuntimeError("AI 影片 shared durable provider 尚未完成設定。")
    values = prepare_request(data, actor, presentation); _enforce_limits(values["actor_username"])
    return repository.create_job(presentation=values["presentation"], actor_username=values["actor_username"], request=values["request"])


class AiVideoJobProcessor:
    def run_job(self, job_id: str) -> bool:
        token = uuid.uuid4().hex; job = repository.claim(job_id, token)
        if not job: return False
        try:
            result = ai_video_runtime.generate_video(job=job, progress_callback=lambda percent, stage, detail: repository.set_progress(job_id, token, percent, stage, detail))
            repository.complete(job_id, token, result)
        except Exception as exc:
            repository.fail(job_id, token, str(exc))
        return True

    def run_next_queued(self) -> bool:
        for job in repository.list_queued(limit=_env_int("AI_VIDEO_JOB_RECOVERY_LIMIT", 10, 1, 50)):
            if self.run_job(str(job.get("id") or "")): return True
        return False

    def recover_stale(self) -> int:
        seconds = _env_int("AI_VIDEO_JOB_STALE_SECONDS", 3600, 300, 43200)
        return repository.requeue_stale_processing((dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=seconds)).isoformat())


def public_job(job: Mapping[str, Any]) -> dict:
    result = {"jobId": job.get("id"), "presentationId": job.get("presentationId"), "status": job.get("status"), "progress": {"percent": job.get("progressPercent", 0), "stage": job.get("progressStage", ""), "detail": job.get("progressDetail", "")}, "createdAt": job.get("createdAt", ""), "updatedAt": job.get("updatedAt", ""), "startedAt": job.get("startedAt", ""), "completedAt": job.get("completedAt", "")}
    if job.get("status") == "completed": result["result"] = job.get("result") or {}
    elif job.get("status") == "failed": result["error"] = str(job.get("error") or "AI 影片產生失敗")
    return result


__all__ = ["AiVideoJobProcessor", "AiVideoLimitError", "enqueue", "prepare_request", "public_job"]
