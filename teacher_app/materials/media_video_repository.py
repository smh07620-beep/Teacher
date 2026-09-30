"""Persistence for reviewed teaching-video composition jobs and artifacts."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Mapping

from teacher_app.common import db as common_db

ACTIVE_STATUSES = ("queued", "processing")
VIDEO_STATUSES = {"draft", "approved"}
MP4_MIME = "video/mp4"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _decode(value: Any, default):
    if isinstance(value, type(default)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, type(default)) else default
        except Exception:
            return default
    return default


def project_job(row) -> dict | None:
    if row is None:
        return None
    item = dict(row)
    for source, target in (
        ("presentation_id", "presentationId"), ("narration_material_id", "narrationMaterialId"),
        ("subtitle_id", "subtitleId"), ("group_key", "group"), ("training_area", "area"),
        ("actor_username", "actorUsername"), ("request_key", "requestKey"),
        ("progress_percent", "progressPercent"), ("progress_stage", "progressStage"),
        ("progress_detail", "progressDetail"), ("claim_token", "claimToken"),
        ("created_at", "createdAt"), ("updated_at", "updatedAt"),
        ("started_at", "startedAt"), ("completed_at", "completedAt"),
    ):
        item[target] = item.pop(source, "")
    item["request"] = _decode(item.pop("request_json", {}), {})
    item["result"] = _decode(item.pop("result_json", {}), {})
    item["progressPercent"] = float(item.get("progressPercent") or 0)
    return item


def project_video(row) -> dict | None:
    if row is None:
        return None
    item = dict(row)
    for source, target in (
        ("request_key", "requestKey"), ("presentation_id", "presentationId"),
        ("narration_material_id", "narrationMaterialId"), ("subtitle_id", "subtitleId"),
        ("group_key", "group"), ("training_area", "area"),
        ("artifact_backend", "artifactBackend"), ("artifact_storage_key", "artifactStorageKey"),
        ("artifact_sha256", "artifactSha256"), ("artifact_bytes", "artifactBytes"),
        ("artifact_mime_type", "artifactMimeType"), ("duration_seconds", "durationSeconds"),
        ("source_presentation_sha256", "sourcePresentationSha256"), ("source_audio_key", "sourceAudioKey"),
        ("source_audio_version", "sourceAudioVersion"), ("source_subtitle_updated_at", "sourceSubtitleUpdatedAt"),
        ("created_by", "createdBy"), ("approved_by", "approvedBy"),
        ("created_at", "createdAt"), ("updated_at", "updatedAt"), ("approved_at", "approvedAt"),
    ):
        item[target] = item.pop(source, "")
    item["artifactBytes"] = int(item.get("artifactBytes") or 0)
    item["durationSeconds"] = float(item.get("durationSeconds") or 0)
    item["sourceAudioVersion"] = int(item.get("sourceAudioVersion") or 1)
    item["provenance"] = _decode(item.pop("provenance_json", {}), {})
    return item


def get_job(job_id: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM media_video_jobs WHERE id={ph}", (job_id,)).fetchone()
    return project_job(row)


def get_job_by_request_key(request_key: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM media_video_jobs WHERE request_key={ph}", (request_key,)).fetchone()
    return project_job(row)


def create_job(values: Mapping[str, Any]) -> dict:
    existing = get_job_by_request_key(str(values["request_key"]))
    if existing:
        return existing
    stamp = now(); payload = json.dumps(values.get("request") or {}, ensure_ascii=False)
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); json_expr = f"{ph}::jsonb" if kind == "postgres" else ph
        conn.execute(
            "INSERT INTO media_video_jobs(id,presentation_id,narration_material_id,subtitle_id,group_key,training_area,"
            "actor_username,request_key,status,request_json,progress_percent,progress_stage,progress_detail,result_json,"
            "error,claim_token,attempts,created_at,updated_at,started_at,completed_at) VALUES("
            f"{','.join([ph] * 9)},{json_expr},{','.join([ph] * 3)},{json_expr},{','.join([ph] * 7)})",
            (values["id"], values["presentation_id"], values["narration_material_id"], values.get("subtitle_id", ""),
             values["group_key"], values["training_area"], values["actor_username"], values["request_key"], "queued",
             payload, 0, "等待影片合成", "工作已排入 AI Worker", "{}", "", "", 0, stamp, stamp, "", ""),
        )
    return get_job(str(values["id"])) or {}


def claim(job_id: str, token: str) -> dict | None:
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cur = conn.execute(
            f"UPDATE media_video_jobs SET status={ph},claim_token={ph},attempts=attempts+1,started_at={ph},updated_at={ph},"
            f"progress_stage={ph},progress_detail={ph} WHERE id={ph} AND status={ph}",
            ("processing", token, stamp, stamp, "影片合成中", "AI Worker 已取得工作", job_id, "queued"),
        )
        if not int(getattr(cur, "rowcount", 0) or 0): return None
        row = conn.execute(f"SELECT * FROM media_video_jobs WHERE id={ph}", (job_id,)).fetchone()
    return project_job(row)


def set_progress(job_id: str, token: str, percent: float, stage: str, detail: str) -> bool:
    stamp = now(); percent = max(0.0, min(99.0, float(percent or 0)))
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cur = conn.execute(
            f"UPDATE media_video_jobs SET progress_percent={ph},progress_stage={ph},progress_detail={ph},updated_at={ph} "
            f"WHERE id={ph} AND status={ph} AND claim_token={ph}",
            (percent, str(stage or "")[:200], str(detail or "")[:1000], stamp, job_id, "processing", token),
        )
    return bool(int(getattr(cur, "rowcount", 0) or 0))


def complete(job_id: str, token: str, result: Mapping[str, Any]) -> bool:
    stamp = now(); payload = json.dumps(dict(result), ensure_ascii=False)
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); expr = f"{ph}::jsonb" if kind == "postgres" else ph
        cur = conn.execute(
            f"UPDATE media_video_jobs SET status={ph},progress_percent={ph},progress_stage={ph},progress_detail={ph},"
            f"result_json={expr},error={ph},completed_at={ph},updated_at={ph} WHERE id={ph} AND status={ph} AND claim_token={ph}",
            ("completed", 100, "影片草稿完成", "請由授課教師預覽並核准影片", payload, "", stamp, stamp, job_id, "processing", token),
        )
    return bool(int(getattr(cur, "rowcount", 0) or 0))


def fail(job_id: str, token: str, error: str) -> bool:
    stamp = now(); message = str(error or "影片合成失敗")[:2000]
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cur = conn.execute(
            f"UPDATE media_video_jobs SET status={ph},progress_percent={ph},progress_stage={ph},progress_detail={ph},error={ph},"
            f"completed_at={ph},updated_at={ph} WHERE id={ph} AND status={ph} AND claim_token={ph}",
            ("failed", 0, "影片合成失敗", message[:1000], message, stamp, stamp, job_id, "processing", token),
        )
    return bool(int(getattr(cur, "rowcount", 0) or 0))


def list_queued(limit: int = 20) -> list[dict]:
    safe = max(1, min(100, int(limit)))
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(f"SELECT * FROM media_video_jobs WHERE status={ph} ORDER BY created_at ASC LIMIT {ph}", ("queued", safe)).fetchall()
    return [project_job(row) for row in rows]


def requeue_stale_processing(cutoff: str) -> int:
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cur = conn.execute(
            f"UPDATE media_video_jobs SET status={ph},claim_token={ph},started_at={ph},updated_at={ph},progress_percent={ph},"
            f"progress_stage={ph},progress_detail={ph} WHERE status={ph} AND updated_at<{ph}",
            ("queued", "", "", stamp, 0, "等待影片合成", "前一個 AI Worker 已中斷，工作已重新排入佇列", "processing", cutoff),
        )
    return int(getattr(cur, "rowcount", 0) or 0)


def get_video(video_id: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM media_videos WHERE id={ph}", (video_id,)).fetchone()
    return project_video(row)


def get_video_by_request_key(request_key: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM media_videos WHERE request_key={ph}", (request_key,)).fetchone()
    return project_video(row)


def create_video(values: Mapping[str, Any]) -> dict:
    existing = get_video_by_request_key(str(values["request_key"]))
    if existing: return existing
    stamp = now(); provenance = json.dumps(values.get("provenance") or {}, ensure_ascii=False, separators=(",", ":"))
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); expr = f"{ph}::jsonb" if kind == "postgres" else ph
        conn.execute(
            "INSERT INTO media_videos(id,request_key,presentation_id,narration_material_id,subtitle_id,group_key,training_area,title,status,"
            "artifact_backend,artifact_storage_key,artifact_sha256,artifact_bytes,artifact_mime_type,duration_seconds,"
            "source_presentation_sha256,source_audio_key,source_audio_version,source_subtitle_updated_at,provenance_json,"
            "created_by,approved_by,created_at,updated_at,approved_at) VALUES("
            f"{','.join([ph] * 19)},{expr},{','.join([ph] * 5)})",
            (values["id"], values["request_key"], values["presentation_id"], values["narration_material_id"], values.get("subtitle_id", ""),
             values["group_key"], values["training_area"], str(values.get("title") or "教學影片")[:255], "draft",
             values["artifact_backend"], values["artifact_storage_key"], values["artifact_sha256"], int(values["artifact_bytes"]), MP4_MIME,
             float(values.get("duration_seconds") or 0), values["source_presentation_sha256"], values["source_audio_key"],
             int(values.get("source_audio_version") or 1), values.get("source_subtitle_updated_at", ""), provenance,
             values["created_by"], "", stamp, stamp, ""),
        )
    return get_video(str(values["id"])) or {}


def approve_video(video_id: str, actor_username: str) -> dict | None:
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cur = conn.execute(
            f"UPDATE media_videos SET status={ph},approved_by={ph},approved_at={ph},updated_at={ph} WHERE id={ph} AND status={ph}",
            ("approved", actor_username, stamp, stamp, video_id, "draft"),
        )
        if not int(getattr(cur, "rowcount", 0) or 0): return get_video(video_id)
    return get_video(video_id)


__all__ = ["ACTIVE_STATUSES", "MP4_MIME", "VIDEO_STATUSES", "approve_video", "claim", "complete", "create_job", "create_video", "fail", "get_job", "get_job_by_request_key", "get_video", "get_video_by_request_key", "list_queued", "now", "requeue_stale_processing", "set_progress"]
