"""Async orchestration for AI-assisted teacher media scripts."""
from __future__ import annotations

import datetime as dt
import os
import uuid
from typing import Any, Mapping

from teacher_app.materials import media_script_repository, media_script_runtime
from teacher_app.materials import repository as material_repository


class MediaScriptLimitError(RuntimeError):
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
        raise ValueError("請選擇教材")
    material = material_repository.get_material(material_id)
    # Draft material is a valid authoring source. Publication state is enforced
    # when the resulting teaching material is formally released, not while a
    # teacher prepares/reviews narration.
    if not material:
        raise LookupError("找不到指定教材")
    try:
        target_minutes = int(data.get("targetMinutes", 5) or 5)
    except (TypeError, ValueError):
        raise ValueError("講稿時間格式錯誤")
    target_minutes = max(1, min(30, target_minutes))
    tone = str(data.get("tone") or "clinical").strip().lower()
    if tone not in {"clinical", "friendly", "brief"}:
        tone = "clinical"
    return {
        "id": f"msjob-{uuid.uuid4().hex}",
        "material_id": material_id,
        "group_key": str(material.get("group") or ""),
        "training_area": str(material.get("area") or ""),
        "actor_username": username,
        "request": {
            "materialId": material_id,
            "targetMinutes": target_minutes,
            "tone": tone,
            "focus": str(data.get("focus") or "").strip()[:500],
        },
    }


def enqueue(data: Mapping[str, Any], actor: Mapping[str, Any] | None) -> dict:
    values = prepare_request(data, actor)
    username = values["actor_username"]
    max_actor = _env_int("MEDIA_SCRIPT_JOB_MAX_ACTIVE_PER_USER", 2, 1, 10)
    max_total = _env_int("MEDIA_SCRIPT_JOB_MAX_ACTIVE_TOTAL", 10, 2, 100)
    max_per_minute = _env_int("MEDIA_SCRIPT_JOB_MAX_PER_MINUTE", 4, 1, 30)
    if media_script_repository.active_count_for_actor(username) >= max_actor:
        raise MediaScriptLimitError(f"目前已有 {max_actor} 個講稿工作排隊或執行中，請完成後再送出")
    if media_script_repository.total_active_count() >= max_total:
        raise MediaScriptLimitError("講稿產生佇列目前已滿，請稍後再試")
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat()
    if media_script_repository.recent_count_for_actor(username, since) >= max_per_minute:
        raise MediaScriptLimitError("講稿產生送出過於頻繁，請稍後再試")
    return media_script_repository.create_job(values)


def run_generation_sync(snapshot: Mapping[str, Any], *, progress_callback=None) -> dict:
    material_id = str(snapshot.get("materialId") or "")
    material = material_repository.get_material(material_id)
    if not material:
        raise RuntimeError("教材已不存在，請重新選擇教材。")
    return media_script_runtime.generate_script(
        material,
        focus=str(snapshot.get("focus") or "")[:500],
        tone=str(snapshot.get("tone") or "clinical")[:30],
        target_minutes=int(snapshot.get("targetMinutes") or 5),
        progress_callback=progress_callback,
    )


class MediaScriptJobProcessor:
    def run_job(self, job_id: str) -> bool:
        token = uuid.uuid4().hex
        job = media_script_repository.claim(job_id, token)
        if not job:
            return False

        def progress(percent, stage, detail):
            media_script_repository.set_progress(job_id, token, percent, stage, detail)

        try:
            media_script_repository.set_progress(job_id, token, 2, "準備講稿", "正在確認教材與文字來源")
            result = run_generation_sync(job.get("request") or {}, progress_callback=progress)
            media_script_repository.complete(job_id, token, result)
        except Exception as exc:
            media_script_repository.fail(job_id, token, str(exc))
        return True

    def run_next_queued(self) -> bool:
        limit = _env_int("MEDIA_SCRIPT_JOB_RECOVERY_LIMIT", 20, 1, 100)
        for job in media_script_repository.list_queued(limit=limit):
            if self.run_job(str(job.get("id") or "")):
                return True
        return False

    def recover_stale(self) -> int:
        minutes = _env_int("MEDIA_SCRIPT_JOB_STALE_MINUTES", 20, 5, 240)
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat()
        return media_script_repository.requeue_stale_processing(cutoff)


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
        result["error"] = str(job.get("error") or "講稿產生失敗")
    return result


__all__ = ["MediaScriptJobProcessor", "MediaScriptLimitError", "enqueue", "prepare_request", "public_job", "run_generation_sync"]
