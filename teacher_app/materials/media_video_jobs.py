"""Async orchestration for reviewed teaching-video composition."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import uuid
from typing import Any, Mapping

from teacher_app.materials import (
    ai_presentation_repository,
    media_subtitle_repository,
    media_video_repository,
    media_video_runtime,
)
from teacher_app.materials import repository as material_repository


class MediaVideoLimitError(RuntimeError):
    pass


def _env_int(name: str, default: int, lower: int, upper: int) -> int:
    try: value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError): value = default
    return max(lower, min(upper, value))


def _username(actor: Mapping[str, Any] | None) -> str:
    return str((actor or {}).get("username") or "").strip()[:100]


def _request_key(*, presentation: dict, narration: dict, subtitle: dict | None) -> str:
    payload = {
        "presentationId": presentation.get("id", ""),
        "presentationSha256": presentation.get("artifactSha256", ""),
        "narrationMaterialId": narration.get("id", ""),
        "narrationVersion": int(narration.get("currentVersion") or 1),
        "narrationKey": narration.get("storageKey", ""),
        "subtitleId": (subtitle or {}).get("id", ""),
        "subtitleUpdatedAt": (subtitle or {}).get("updatedAt", ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def prepare_request(data: Mapping[str, Any], actor: Mapping[str, Any] | None) -> dict:
    username = _username(actor)
    if not username: raise ValueError("無法確認目前登入帳號")
    presentation_id = str(data.get("presentationId") or "").strip()[:120]
    narration_id = str(data.get("narrationMaterialId") or "").strip()[:120]
    subtitle_id = str(data.get("subtitleId") or "").strip()[:120]
    if not presentation_id or not narration_id:
        raise ValueError("請選擇已核准 PowerPoint 與 AI 語音教材")
    presentation = ai_presentation_repository.get_presentation(presentation_id)
    if not presentation:
        raise LookupError("找不到指定 PowerPoint")
    if presentation.get("status") != "approved" or not presentation.get("approvedBy") or not presentation.get("approvedAt"):
        raise ValueError("只有授課教師已核准的 PowerPoint revision 可以產生影片")
    if not presentation.get("artifactStorageKey") or not presentation.get("artifactSha256") or int(presentation.get("artifactBytes") or 0) <= 0:
        raise ValueError("PowerPoint 尚未產生可驗證的共享 artifact")
    narration = material_repository.get_material(narration_id)
    if not narration:
        raise LookupError("找不到指定 AI 語音教材")
    meta = narration.get("storageMeta") or {}
    if narration.get("storageBackend") != "r2" or not narration.get("storageKey"):
        raise ValueError("目前影片合成只接受已保存於 R2 的 AI 語音教材")
    if meta.get("mediaKind") != "ai_narration" or not meta.get("teacherApprovedBy") or not meta.get("teacherApprovedAt"):
        raise ValueError("語音教材必須來自授課教師已核准的講稿")
    if narration.get("group") != presentation.get("group") or narration.get("area") != presentation.get("area"):
        raise ValueError("PowerPoint 與語音教材不在相同組別/訓練範圍")
    subtitle = None
    if subtitle_id:
        subtitle = media_subtitle_repository.get_subtitle(subtitle_id)
        if not subtitle or subtitle.get("status") != "approved":
            raise ValueError("指定字幕尚未由授課教師核准")
        if subtitle.get("materialId") != narration_id:
            raise ValueError("字幕來源必須是本次使用的 AI 語音教材")
        if subtitle.get("group") != presentation.get("group") or subtitle.get("area") != presentation.get("area"):
            raise ValueError("字幕不在相同組別/訓練範圍")
        if int(subtitle.get("sourceVersion") or 1) != int(narration.get("currentVersion") or 1):
            raise ValueError("字幕來源語音已有新版，請重新產生並核准字幕")
    request_key = _request_key(presentation=presentation, narration=narration, subtitle=subtitle)
    return {
        "id": f"mvjob-{uuid.uuid4().hex}",
        "presentation_id": presentation_id,
        "narration_material_id": narration_id,
        "subtitle_id": subtitle_id,
        "group_key": str(presentation.get("group") or ""),
        "training_area": str(presentation.get("area") or ""),
        "actor_username": username,
        "request_key": request_key,
        "request": {"presentationId": presentation_id, "narrationMaterialId": narration_id, "subtitleId": subtitle_id},
    }


def _enforce_queue_limits(username: str) -> None:
    # The heavy FFmpeg/LibreOffice lane intentionally stays conservative.
    max_total = _env_int("MEDIA_VIDEO_JOB_MAX_ACTIVE_TOTAL", 2, 1, 10)
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat()
    # Keep this query local and explicit until video jobs need a broader admin metric API.
    from teacher_app.common import db as common_db
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        actor = conn.execute(
            f"SELECT COUNT(*) AS n FROM media_video_jobs WHERE actor_username={ph} AND status IN ({ph},{ph})",
            (username, *media_video_repository.ACTIVE_STATUSES),
        ).fetchone()
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM media_video_jobs WHERE status IN ({ph},{ph})",
            media_video_repository.ACTIVE_STATUSES,
        ).fetchone()
        recent = conn.execute(
            f"SELECT COUNT(*) AS n FROM media_video_jobs WHERE actor_username={ph} AND created_at>={ph}",
            (username, since),
        ).fetchone()
    if int(dict(actor).get("n", 0) or 0) >= 1:
        raise MediaVideoLimitError("目前已有影片合成工作排隊或執行中")
    if int(dict(total).get("n", 0) or 0) >= max_total:
        raise MediaVideoLimitError("影片合成佇列目前已滿，請稍後再試")
    if int(dict(recent).get("n", 0) or 0) >= 2:
        raise MediaVideoLimitError("影片合成送出過於頻繁，請稍後再試")


def enqueue(data: Mapping[str, Any], actor: Mapping[str, Any] | None) -> dict:
    if not media_video_runtime.configured():
        raise RuntimeError("影片 Worker 尚未完成 FFmpeg / LibreOffice / R2 設定")
    values = prepare_request(data, actor)
    existing = media_video_repository.get_job_by_request_key(values["request_key"])
    if existing: return existing
    _enforce_queue_limits(values["actor_username"])
    return media_video_repository.create_job(values)


class MediaVideoJobProcessor:
    def run_job(self, job_id: str) -> bool:
        token = uuid.uuid4().hex
        job = media_video_repository.claim(job_id, token)
        if not job: return False
        def progress(percent, stage, detail):
            media_video_repository.set_progress(job_id, token, percent, stage, detail)
        try:
            result = media_video_runtime.generate_video(job=job, progress_callback=progress)
            media_video_repository.complete(job_id, token, result)
        except Exception as exc:
            media_video_repository.fail(job_id, token, str(exc))
        return True

    def run_next_queued(self) -> bool:
        limit = _env_int("MEDIA_VIDEO_JOB_RECOVERY_LIMIT", 5, 1, 20)
        for job in media_video_repository.list_queued(limit=limit):
            if self.run_job(str(job.get("id") or "")): return True
        return False

    def recover_stale(self) -> int:
        minutes = _env_int("MEDIA_VIDEO_JOB_STALE_MINUTES", 60, 15, 360)
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat()
        return media_video_repository.requeue_stale_processing(cutoff)


def public_job(job: Mapping[str, Any]) -> dict:
    result = {
        "jobId": job.get("id"), "status": job.get("status", "queued"),
        "presentationId": job.get("presentationId"), "narrationMaterialId": job.get("narrationMaterialId"),
        "subtitleId": job.get("subtitleId", ""),
        "progress": {"percent": job.get("progressPercent", 0), "stage": job.get("progressStage", ""), "detail": job.get("progressDetail", "")},
        "createdAt": job.get("createdAt", ""), "updatedAt": job.get("updatedAt", ""),
    }
    if job.get("status") == "completed": result["result"] = dict(job.get("result") or {})
    if job.get("status") == "failed": result["error"] = str(job.get("error") or "影片合成失敗")
    return result


__all__ = ["MediaVideoJobProcessor", "MediaVideoLimitError", "enqueue", "prepare_request", "public_job"]
