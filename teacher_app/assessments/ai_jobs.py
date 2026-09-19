"""Persistent async orchestration for AI question-generation requests."""
from __future__ import annotations

import datetime as dt
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from teacher_app.assessments import ai_job_repository, repository
from teacher_app.common import privacy as ai_privacy
from teacher_app.materials import repository as material_repository


class AiJobLimitError(RuntimeError):
    pass


def _env_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(lower, min(upper, value))


def _actor_username(actor: Mapping[str, Any] | None) -> str:
    return str((actor or {}).get("username") or "").strip()[:100]


def prepare_request(data: Mapping[str, Any], runtime, actor: Mapping[str, Any] | None) -> dict:
    username = _actor_username(actor)
    if not username:
        raise ValueError("無法確認目前登入帳號")
    category_id = str(data.get("quizCategoryId") or "").strip()
    category = repository.get_category_full(category_id)
    if not category:
        raise LookupError("找不到考題頁籤。請重新整理後台後再試。")

    raw_ids = data.get("materialIds")
    if not isinstance(raw_ids, list):
        one = str(data.get("materialId") or "").strip()
        raw_ids = [one] if one else []
    material_ids: list[str] = []
    for value in raw_ids:
        material_id = str(value or "").strip()
        if material_id and material_id not in material_ids:
            material_ids.append(material_id)
    if not material_ids:
        raise ValueError("請至少選擇一份教材")
    if len(material_ids) > runtime.max_materials:
        raise ValueError(f"一次最多選 {runtime.max_materials} 份教材")

    for material_id in material_ids:
        material = material_repository.get_material(material_id)
        if not material or not material.get("active", True):
            raise LookupError(f"找不到指定教材：{material_id}")
        if material.get("group") != category.get("group") or material.get("area") != category.get("area"):
            raise ValueError("所選教材與考卷不屬於同一訓練區/組別")

    try:
        count = int(data.get("count", 5) or 5)
    except (TypeError, ValueError):
        raise ValueError("AI 題數格式錯誤")
    count = max(1, min(runtime.max_questions, count))
    request_snapshot = {
        "quizCategoryId": category_id,
        "materialIds": material_ids,
        "count": count,
        "questionType": str(data.get("questionType", "mixed") or "mixed")[:40],
        "difficulty": str(data.get("difficulty", "standard") or "standard")[:40],
        "strategy": str(data.get("strategy", "auto") or "auto")[:30],
        "focus": ai_privacy.deidentify_external_text(data.get("focus", "")).strip()[:500],
    }
    return {
        "id": f"aijob-{uuid.uuid4().hex}",
        "quiz_category_id": category_id,
        "group_key": str(category.get("group") or ""),
        "training_area": str(category.get("area") or ""),
        "actor_username": username,
        "request": request_snapshot,
    }


def enqueue(data: Mapping[str, Any], runtime, actor: Mapping[str, Any] | None) -> dict:
    values = prepare_request(data, runtime, actor)
    username = values["actor_username"]
    max_actor_active = _env_int("AI_QUESTION_JOB_MAX_ACTIVE_PER_USER", 3, 1, 10)
    max_total_active = _env_int("AI_QUESTION_JOB_MAX_ACTIVE_TOTAL", 20, 2, 100)
    max_per_minute = _env_int("AI_QUESTION_JOB_MAX_PER_MINUTE", 6, 1, 60)
    if ai_job_repository.active_count_for_actor(username) >= max_actor_active:
        raise AiJobLimitError(f"目前已有 {max_actor_active} 個 AI 出題工作排隊或執行中，請完成後再送出")
    if ai_job_repository.total_active_count() >= max_total_active:
        raise AiJobLimitError("AI 出題佇列目前已滿，請稍後再試")
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat()
    if ai_job_repository.recent_count_for_actor(username, since) >= max_per_minute:
        raise AiJobLimitError("AI 出題送出過於頻繁，請稍後再試")
    return ai_job_repository.create_job(values)


def run_generation_sync(
    runtime,
    snapshot: Mapping[str, Any],
    *,
    progress_callback: Callable[..., Any] | None = None,
    progress_id: str = "async-ai-job",
) -> dict:
    if not ai_privacy.external_enabled():
        raise RuntimeError("院方目前已停用外部 AI 處理。")
    material_ids = list(snapshot.get("materialIds") or [])
    materials = []
    for material_id in material_ids:
        material = material_repository.get_material(str(material_id))
        if not material or not material.get("active", True):
            raise RuntimeError(f"教材已不存在或停用：{material_id}")
        filename = str(material.get("filename") or material.get("storageFilename") or "")
        if Path(filename).suffix.lower() in ai_privacy.MEDIA_EXT and not ai_privacy.external_media_allowed():
            raise RuntimeError("院方目前禁止將圖片/影音送往外部 AI；請改用文字教材或由管理者明確開啟外部媒體處理。")
        materials.append(material)
    requested_strategy = str(snapshot.get("strategy") or "auto")[:30]
    questions, source_title, source_kinds = runtime.generate_ai_questions_from_materials(
        materials,
        category_id=str(snapshot.get("quizCategoryId") or ""),
        count=snapshot.get("count", 5),
        qtype=str(snapshot.get("questionType") or "mixed"),
        difficulty=str(snapshot.get("difficulty") or "standard"),
        focus=str(snapshot.get("focus") or "")[:500],
        strategy=requested_strategy,
        progress_id=progress_id,
        progress_callback=progress_callback,
    )
    applied_strategy = runtime.infer_ai_strategy(materials) if requested_strategy == "auto" else requested_strategy
    provider = runtime.active_ai_provider()
    return {
        "ok": True,
        "questions": questions,
        "sourceTitle": source_title,
        "sourceCount": len(materials),
        "sourceKinds": source_kinds,
        "sourceMode": "multimedia" if any(kind in {"image", "video", "audio"} for kind in source_kinds) else "text",
        "provider": provider,
        "model": runtime.ai_model_name(),
        "strategyRequested": requested_strategy,
        "strategyApplied": applied_strategy,
    }


class AiQuestionJobProcessor:
    """Claim-bound AI job processor intended for a dedicated worker process."""

    def __init__(self, runtime):
        self.runtime = runtime

    def run_job(self, job_id: str) -> bool:
        token = uuid.uuid4().hex
        job = ai_job_repository.claim(job_id, token)
        if not job:
            return False

        def progress(_progress_id, percent, stage, detail, **_kwargs):
            ai_job_repository.set_progress(job_id, token, percent, stage, detail)

        try:
            ai_job_repository.set_progress(job_id, token, 2, "準備 AI 出題", "正在載入教材並開始背景分析")
            result = run_generation_sync(
                self.runtime,
                job.get("request") or {},
                progress_callback=progress,
                progress_id=job_id,
            )
            ai_job_repository.complete(job_id, token, result)
        except Exception as exc:
            ai_job_repository.fail(job_id, token, str(exc))
        return True

    def recover_stale(self) -> int:
        stale_minutes = _env_int("AI_QUESTION_JOB_STALE_MINUTES", 20, 5, 240)
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=stale_minutes)).isoformat()
        return ai_job_repository.requeue_stale_processing(cutoff)

    def run_next_queued(self) -> bool:
        for job in ai_job_repository.list_queued(limit=_env_int("AI_QUESTION_JOB_RECOVERY_LIMIT", 20, 1, 100)):
            if self.run_job(str(job.get("id") or "")):
                return True
        return False


def public_job(job: Mapping[str, Any]) -> dict:
    status = str(job.get("status") or "queued")
    body = {
        "jobId": job.get("id"),
        "status": status,
        "quizCategoryId": job.get("quizCategoryId"),
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
        body["result"] = job.get("result") or {}
    elif status == "failed":
        body["error"] = str(job.get("error") or "AI 出題失敗")
    return body


__all__ = [
    "AiJobLimitError",
    "AiQuestionJobProcessor",
    "enqueue",
    "prepare_request",
    "public_job",
    "run_generation_sync",
]
