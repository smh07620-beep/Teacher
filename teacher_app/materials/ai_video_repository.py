"""Persistence for immutable AI presentation video revisions and queue jobs."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any, Mapping

from teacher_app.common import db as common_db

ACTIVE_STATUSES = ("queued", "processing")
VIDEO_STATUSES = {"draft", "approved", "published", "superseded"}
MP4_MIME = "video/mp4"
_DURABLE = {"r2", "oci", "gdrive", "mega", "local"}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _decode(value: Any, default):
    if isinstance(value, type(default)):
        return value
    try:
        parsed = json.loads(value) if isinstance(value, str) and value else default
        return parsed if isinstance(parsed, type(default)) else default
    except Exception:
        return default


def _json(kind: str, ph: str) -> str:
    return f"{ph}::jsonb" if kind == "postgres" else ph


def _job(row):
    if not row:
        return None
    item = dict(row)
    return {"id": item.get("id", ""), "presentationId": item.get("presentation_id", ""),
            "presentationFamilyId": item.get("presentation_family_id", ""), "presentationRevision": int(item.get("presentation_revision") or 1),
            "group": item.get("group_key", ""), "area": item.get("training_area", ""), "actorUsername": item.get("actor_username", ""),
            "status": item.get("status", ""), "request": _decode(item.get("request_json"), {}), "result": _decode(item.get("result_json"), {}),
            "progressPercent": float(item.get("progress_percent") or 0), "progressStage": item.get("progress_stage", ""),
            "progressDetail": item.get("progress_detail", ""), "error": item.get("error", ""), "claimToken": item.get("claim_token", ""),
            "attempts": int(item.get("attempts") or 0), "createdAt": item.get("created_at", ""), "updatedAt": item.get("updated_at", ""),
            "startedAt": item.get("started_at", ""), "completedAt": item.get("completed_at", "")}


def _video(row):
    if not row:
        return None
    item = dict(row); video_id = str(item.get("id") or "")
    return {"id": video_id, "videoFamilyId": item.get("video_family_id") or video_id, "parentRevisionId": item.get("parent_revision_id", ""),
            "revisionNumber": int(item.get("revision_number") or 1), "presentationId": item.get("presentation_id", ""),
            "presentationFamilyId": item.get("presentation_family_id", ""), "presentationRevision": int(item.get("presentation_revision") or 1),
            "presentationSha256": item.get("presentation_sha256", ""), "group": item.get("group_key", ""), "area": item.get("training_area", ""),
            "title": item.get("title", ""), "status": item.get("status", "draft"), "artifactBackend": item.get("artifact_backend", ""),
            "artifactStorageKey": item.get("artifact_storage_key", ""), "artifactStorageFilename": item.get("artifact_storage_filename", ""),
            "artifactSha256": item.get("artifact_sha256", ""), "artifactBytes": int(item.get("artifact_bytes") or 0),
            "artifactMimeType": item.get("artifact_mime_type", ""), "durationSeconds": float(item.get("duration_seconds") or 0),
            "timeline": _decode(item.get("timeline_json"), []), "vttText": item.get("vtt_text", ""), "srtText": item.get("srt_text", ""),
            "ttsProvider": item.get("tts_provider", ""), "ttsModel": item.get("tts_model", ""), "ttsVoice": item.get("tts_voice", ""),
            "sourceJobId": item.get("source_job_id", ""), "createdBy": item.get("created_by", ""), "updatedBy": item.get("updated_by", ""),
            "approvedBy": item.get("approved_by", ""), "approvedAt": item.get("approved_at", ""), "publishedAt": item.get("published_at", ""),
            "createdAt": item.get("created_at", ""), "updatedAt": item.get("updated_at", "")}


def create_job(*, presentation: Mapping[str, Any], actor_username: str, request: Mapping[str, Any]) -> dict:
    job_id, stamp = f"vidjob-{uuid.uuid4().hex}", now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); j = _json(kind, ph)
        conn.execute("INSERT INTO ai_video_jobs(id,presentation_id,presentation_family_id,presentation_revision,group_key,training_area,actor_username,status,request_json,progress_percent,progress_stage,progress_detail,result_json,error,claim_token,attempts,created_at,updated_at,started_at,completed_at) VALUES(" + f"{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{j},{ph},{ph},{ph},{j},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
                     (job_id, presentation["id"], presentation.get("presentationFamilyId", ""), int(presentation.get("revisionNumber") or 1), presentation["group"], presentation["area"], actor_username, "queued", json.dumps(dict(request), ensure_ascii=False), 0, "等待 AI 影片", "工作已排入 AI Worker", "{}", "", "", 0, stamp, stamp, "", ""))
    return get_job(job_id) or {}


def get_job(job_id: str):
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind); row = conn.execute(f"SELECT * FROM ai_video_jobs WHERE id={ph}", (job_id,)).fetchone()
    return _job(row)


def list_queued(limit=20):
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind); rows = conn.execute(f"SELECT * FROM ai_video_jobs WHERE status={ph} ORDER BY created_at LIMIT {ph}", ("queued", max(1, min(100, int(limit))))).fetchall()
    return [_job(row) for row in rows]


def _count(sql: str, params: tuple) -> int:
    with common_db.read_connection() as (conn, kind):
        row = conn.execute(sql.format(ph=common_db.placeholder(kind)), params).fetchone()
    return int(dict(row).get("n", 0) or 0)


def active_count_for_actor(username: str) -> int:
    return _count("SELECT COUNT(*) n FROM ai_video_jobs WHERE actor_username={ph} AND status IN ({ph},{ph})", (username, *ACTIVE_STATUSES))


def total_active_count() -> int:
    return _count("SELECT COUNT(*) n FROM ai_video_jobs WHERE status IN ({ph},{ph})", ACTIVE_STATUSES)


def recent_count_for_actor(username: str, since: str) -> int:
    return _count("SELECT COUNT(*) n FROM ai_video_jobs WHERE actor_username={ph} AND created_at>={ph}", (username, since))


def claim(job_id: str, token: str):
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); cur = conn.execute(f"UPDATE ai_video_jobs SET status={ph},claim_token={ph},attempts=attempts+1,started_at={ph},updated_at={ph},progress_stage={ph},progress_detail={ph} WHERE id={ph} AND status={ph}", ("processing", token, stamp, stamp, "AI 影片處理中", "AI Worker 已取得工作", job_id, "queued"))
        if not int(cur.rowcount or 0): return None
        row = conn.execute(f"SELECT * FROM ai_video_jobs WHERE id={ph}", (job_id,)).fetchone()
    return _job(row)


def set_progress(job_id: str, token: str, percent: float, stage: str, detail: str) -> bool:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); cur = conn.execute(f"UPDATE ai_video_jobs SET progress_percent={ph},progress_stage={ph},progress_detail={ph},updated_at={ph} WHERE id={ph} AND status={ph} AND claim_token={ph}", (max(0, min(99, float(percent))), str(stage)[:200], str(detail)[:1000], now(), job_id, "processing", token))
    return bool(int(cur.rowcount or 0))


def complete(job_id: str, token: str, result: Mapping[str, Any]) -> bool:
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); j = _json(kind, ph); cur = conn.execute(f"UPDATE ai_video_jobs SET status={ph},progress_percent={ph},progress_stage={ph},progress_detail={ph},result_json={j},error={ph},completed_at={ph},updated_at={ph} WHERE id={ph} AND status={ph} AND claim_token={ph}", ("completed", 100, "AI 影片完成", "請由授課教師預覽、核准與發布", json.dumps(dict(result), ensure_ascii=False), "", stamp, stamp, job_id, "processing", token))
    return bool(int(cur.rowcount or 0))


def fail(job_id: str, token: str, error: str) -> bool:
    stamp, message = now(), str(error or "AI 影片產生失敗")[:2000]
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); cur = conn.execute(f"UPDATE ai_video_jobs SET status={ph},progress_percent={ph},progress_stage={ph},progress_detail={ph},error={ph},completed_at={ph},updated_at={ph} WHERE id={ph} AND status={ph} AND claim_token={ph}", ("failed", 0, "AI 影片產生失敗", message[:1000], message, stamp, stamp, job_id, "processing", token))
    return bool(int(cur.rowcount or 0))


def requeue_stale_processing(cutoff: str) -> int:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); cur = conn.execute(f"UPDATE ai_video_jobs SET status={ph},claim_token={ph},started_at={ph},updated_at={ph},progress_percent={ph},progress_stage={ph},progress_detail={ph} WHERE status={ph} AND updated_at<{ph}", ("queued", "", "", now(), 0, "等待 AI 影片", "前一個 AI Worker 已中斷，工作已重新排入佇列", "processing", cutoff))
    return int(cur.rowcount or 0)


def get_video(video_id: str):
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind); row = conn.execute(f"SELECT * FROM ai_presentation_videos WHERE id={ph}", (video_id,)).fetchone()
    return _video(row)


def get_video_by_source_job(job_id: str):
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind); row = conn.execute(f"SELECT * FROM ai_presentation_videos WHERE source_job_id={ph}", (job_id,)).fetchone()
    return _video(row)


def list_videos(presentation_id: str, limit=50):
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind); rows = conn.execute(f"SELECT * FROM ai_presentation_videos WHERE presentation_id={ph} ORDER BY updated_at DESC LIMIT {ph}", (presentation_id, max(1, min(100, int(limit))))).fetchall()
    return [_video(row) for row in rows]


def create_video(*, presentation: Mapping[str, Any], title: str, artifact: Mapping[str, Any], duration_seconds: float, timeline: list, vtt_text: str, srt_text: str, tts: Mapping[str, str], source_job_id: str, actor_username: str):
    backend, key, digest, size, mime = str(artifact.get("backend") or "").lower(), str(artifact.get("key") or ""), str(artifact.get("sha256") or "").lower(), int(artifact.get("byteSize") or 0), str(artifact.get("mimeType") or "")
    if backend not in _DURABLE or not key or len(digest) != 64 or size <= 0 or mime != MP4_MIME or duration_seconds <= 0:
        raise ValueError("AI 影片 durable artifact metadata 不完整。")
    video_id, stamp = f"vid-{uuid.uuid4().hex}", now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); j = _json(kind, ph)
        conn.execute("INSERT INTO ai_presentation_videos(id,video_family_id,parent_revision_id,revision_number,presentation_id,presentation_family_id,presentation_revision,presentation_sha256,group_key,training_area,title,status,artifact_backend,artifact_storage_key,artifact_storage_filename,artifact_sha256,artifact_bytes,artifact_mime_type,duration_seconds,timeline_json,vtt_text,srt_text,tts_provider,tts_model,tts_voice,source_job_id,created_by,updated_by,approved_by,approved_at,published_at,created_at,updated_at) VALUES(" + f"{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{j},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})", (video_id, video_id, "", 1, presentation["id"], presentation.get("presentationFamilyId", ""), int(presentation.get("revisionNumber") or 1), presentation.get("artifactSha256", ""), presentation["group"], presentation["area"], title[:255], "draft", backend, key, artifact.get("filename", ""), digest, size, mime, float(duration_seconds), json.dumps(timeline, ensure_ascii=False), vtt_text, srt_text, tts.get("provider", ""), tts.get("model", ""), tts.get("voice", ""), source_job_id, actor_username, actor_username, "", "", "", stamp, stamp))
    return get_video(video_id) or {}


def set_status(video_id: str, *, status: str, actor_username: str):
    if status not in VIDEO_STATUSES: raise ValueError("不支援的 AI 影片狀態。")
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); row = conn.execute(f"SELECT status,approved_by,approved_at FROM ai_presentation_videos WHERE id={ph}", (video_id,)).fetchone()
        if not row: return None
        previous = str(dict(row).get("status") or "draft")
        if status == "approved" and previous not in {"draft", "approved"}: raise ValueError("只有 draft AI 影片可核准。")
        if status == "published" and previous not in {"approved", "published"}: raise ValueError("AI 影片必須先由授課教師核准。")
        approved_by = str(dict(row).get("approved_by") or actor_username) if status == "published" else (actor_username if status == "approved" else "")
        approved_at = str(dict(row).get("approved_at") or stamp) if status == "published" else (stamp if status == "approved" else "")
        conn.execute(f"UPDATE ai_presentation_videos SET status={ph},updated_by={ph},updated_at={ph},approved_by={ph},approved_at={ph},published_at={ph} WHERE id={ph}", (status, actor_username, stamp, approved_by, approved_at, stamp if status == "published" else "", video_id))
    return get_video(video_id)


def publication_receipt_key(video_id: str) -> str:
    return "vidpub-" + hashlib.sha256(video_id.encode("utf-8")).hexdigest()


def create_publication(*, video_id: str, actor_username: str, receipt: Mapping[str, Any]):
    key = publication_receipt_key(video_id)
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); j = _json(kind, ph); row = conn.execute(f"SELECT * FROM ai_video_publications WHERE receipt_key={ph}", (key,)).fetchone()
        if row: return {"id": dict(row).get("id"), "videoId": dict(row).get("video_id"), "receiptKey": dict(row).get("receipt_key"), "receipt": _decode(dict(row).get("receipt_json"), {})}
        pub_id = f"vidpub-{uuid.uuid4().hex}"; stamp = now()
        conn.execute(f"INSERT INTO ai_video_publications(id,video_id,receipt_key,receipt_json,created_by,created_at) VALUES({ph},{ph},{ph},{j},{ph},{ph})", (pub_id, video_id, key, json.dumps(dict(receipt), ensure_ascii=False), actor_username, stamp))
    return {"id": pub_id, "videoId": video_id, "receiptKey": key, "receipt": dict(receipt)}


__all__ = ["ACTIVE_STATUSES", "MP4_MIME", "active_count_for_actor", "claim", "complete", "create_job", "create_publication", "create_video", "fail", "get_job", "get_video", "get_video_by_source_job", "list_queued", "list_videos", "now", "publication_receipt_key", "recent_count_for_actor", "requeue_stale_processing", "set_progress", "set_status", "total_active_count"]
