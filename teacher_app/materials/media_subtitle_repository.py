"""Persistence for AI subtitle jobs and teacher-reviewed caption drafts."""
from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any, Mapping

from teacher_app.common import db as common_db


ACTIVE_STATUSES = ("queued", "processing")
SUBTITLE_STATUSES = {"draft", "approved"}


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
    item["materialId"] = item.pop("material_id", "")
    item["group"] = item.pop("group_key", "")
    item["area"] = item.pop("training_area", "")
    item["actorUsername"] = item.pop("actor_username", "")
    item["request"] = _decode(item.pop("request_json", {}), {})
    item["result"] = _decode(item.pop("result_json", {}), {})
    item["progressPercent"] = float(item.pop("progress_percent", 0) or 0)
    item["progressStage"] = str(item.pop("progress_stage", "") or "")
    item["progressDetail"] = str(item.pop("progress_detail", "") or "")
    item["claimToken"] = str(item.pop("claim_token", "") or "")
    item["createdAt"] = str(item.pop("created_at", "") or "")
    item["updatedAt"] = str(item.pop("updated_at", "") or "")
    item["startedAt"] = str(item.pop("started_at", "") or "")
    item["completedAt"] = str(item.pop("completed_at", "") or "")
    return item


def project_subtitle(row) -> dict | None:
    if row is None:
        return None
    item = dict(row)
    item["materialId"] = item.pop("material_id", "")
    item["group"] = item.pop("group_key", "")
    item["area"] = item.pop("training_area", "")
    item["vttText"] = str(item.pop("vtt_text", "") or "")
    item["srtText"] = str(item.pop("srt_text", "") or "")
    item["transcriptText"] = str(item.pop("transcript_text", "") or "")
    item["fallbackUsed"] = bool(item.pop("fallback_used", False))
    item["sourceVersion"] = max(1, int(item.pop("source_version", 1) or 1))
    item["sourceSha256"] = str(item.pop("source_sha256", "") or "")
    item["sourceKind"] = str(item.pop("source_kind", "") or "")
    item["sourceLocator"] = str(item.pop("source_locator", "") or "")
    item["sourceJobId"] = str(item.pop("source_job_id", "") or "")
    item["createdBy"] = str(item.pop("created_by", "") or "")
    item["updatedBy"] = str(item.pop("updated_by", "") or "")
    item["approvedBy"] = str(item.pop("approved_by", "") or "")
    item["createdAt"] = str(item.pop("created_at", "") or "")
    item["updatedAt"] = str(item.pop("updated_at", "") or "")
    item["approvedAt"] = str(item.pop("approved_at", "") or "")
    return item


def create_job(values: Mapping[str, Any]) -> dict:
    stamp = str(values.get("created_at") or now())
    request_json = json.dumps(values.get("request") or {}, ensure_ascii=False)
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        json_expr = f"{ph}::jsonb" if kind == "postgres" else ph
        conn.execute(
            "INSERT INTO media_subtitle_jobs("
            "id,material_id,group_key,training_area,actor_username,status,request_json,"
            "progress_percent,progress_stage,progress_detail,result_json,error,claim_token,attempts,"
            "created_at,updated_at,started_at,completed_at) VALUES("
            f"{ph},{ph},{ph},{ph},{ph},{ph},{json_expr},{ph},{ph},{ph},{json_expr},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
            (
                values["id"], values["material_id"], values["group_key"], values["training_area"],
                values["actor_username"], "queued", request_json, 0, "等待 AI 字幕", "工作已排入 AI Worker",
                "{}", "", "", 0, stamp, stamp, "", "",
            ),
        )
    return get_job(str(values["id"])) or {}


def get_job(job_id: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM media_subtitle_jobs WHERE id={ph}", (job_id,)).fetchone()
    return project_job(row)


def active_count_for_actor(username: str) -> int:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM media_subtitle_jobs WHERE actor_username={ph} AND status IN ({ph},{ph})",
            (username, *ACTIVE_STATUSES),
        ).fetchone()
    return int(dict(row).get("n", 0) or 0)


def total_active_count() -> int:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM media_subtitle_jobs WHERE status IN ({ph},{ph})", ACTIVE_STATUSES
        ).fetchone()
    return int(dict(row).get("n", 0) or 0)


def recent_count_for_actor(username: str, since: str) -> int:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM media_subtitle_jobs WHERE actor_username={ph} AND created_at>={ph}",
            (username, since),
        ).fetchone()
    return int(dict(row).get("n", 0) or 0)


def claim(job_id: str, token: str) -> dict | None:
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"UPDATE media_subtitle_jobs SET status={ph},claim_token={ph},attempts=attempts+1,started_at={ph},updated_at={ph},"
            f"progress_stage={ph},progress_detail={ph} WHERE id={ph} AND status={ph}",
            ("processing", token, stamp, stamp, "AI 字幕處理中", "AI Worker 已取得工作", job_id, "queued"),
        )
        if not int(getattr(cursor, "rowcount", 0) or 0):
            return None
        row = conn.execute(f"SELECT * FROM media_subtitle_jobs WHERE id={ph}", (job_id,)).fetchone()
    return project_job(row)


def set_progress(job_id: str, token: str, percent: float, stage: str, detail: str) -> bool:
    stamp = now()
    percent = max(0.0, min(99.0, float(percent or 0)))
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"UPDATE media_subtitle_jobs SET progress_percent={ph},progress_stage={ph},progress_detail={ph},updated_at={ph} "
            f"WHERE id={ph} AND status={ph} AND claim_token={ph}",
            (percent, str(stage or "")[:200], str(detail or "")[:1000], stamp, job_id, "processing", token),
        )
    return bool(int(getattr(cursor, "rowcount", 0) or 0))


def complete(job_id: str, token: str, result: Mapping[str, Any]) -> bool:
    stamp = now()
    payload = json.dumps(dict(result), ensure_ascii=False)
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        result_expr = f"{ph}::jsonb" if kind == "postgres" else ph
        cursor = conn.execute(
            f"UPDATE media_subtitle_jobs SET status={ph},progress_percent={ph},progress_stage={ph},progress_detail={ph},"
            f"result_json={result_expr},error={ph},completed_at={ph},updated_at={ph} "
            f"WHERE id={ph} AND status={ph} AND claim_token={ph}",
            ("completed", 100, "AI 字幕草稿完成", "請由教師確認字幕內容並核准後才會提供學員使用", payload, "", stamp, stamp, job_id, "processing", token),
        )
    return bool(int(getattr(cursor, "rowcount", 0) or 0))


def fail(job_id: str, token: str, error: str) -> bool:
    stamp = now()
    message = str(error or "AI 字幕產生失敗")[:2000]
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"UPDATE media_subtitle_jobs SET status={ph},progress_percent={ph},progress_stage={ph},progress_detail={ph},error={ph},"
            f"completed_at={ph},updated_at={ph} WHERE id={ph} AND status={ph} AND claim_token={ph}",
            ("failed", 0, "AI 字幕產生失敗", message[:1000], message, stamp, stamp, job_id, "processing", token),
        )
    return bool(int(getattr(cursor, "rowcount", 0) or 0))


def list_queued(limit: int = 20) -> list[dict]:
    safe_limit = max(1, min(100, int(limit)))
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM media_subtitle_jobs WHERE status={ph} ORDER BY created_at ASC LIMIT {ph}",
            ("queued", safe_limit),
        ).fetchall()
    return [project_job(row) for row in rows]


def requeue_stale_processing(cutoff: str) -> int:
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"UPDATE media_subtitle_jobs SET status={ph},claim_token={ph},started_at={ph},updated_at={ph},progress_percent={ph},"
            f"progress_stage={ph},progress_detail={ph} WHERE status={ph} AND updated_at<{ph}",
            ("queued", "", "", stamp, 0, "等待 AI 字幕", "前一個 AI Worker 已中斷，工作已重新排入佇列", "processing", cutoff),
        )
    return int(getattr(cursor, "rowcount", 0) or 0)


def create_subtitle(*, material_id: str, group_key: str, training_area: str, language: str, label: str,
                    vtt_text: str, srt_text: str, transcript_text: str, provider: str, model: str,
                    fallback_used: bool, source_version: int, source_sha256: str, source_kind: str,
                    source_locator: str, source_job_id: str, actor_username: str) -> dict:
    subtitle_id = f"msub-{uuid.uuid4().hex}"
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        fallback_value = bool(fallback_used) if kind == "postgres" else int(bool(fallback_used))
        conn.execute(
            "INSERT INTO media_subtitles("
            "id,material_id,group_key,training_area,language,label,status,vtt_text,srt_text,transcript_text,provider,model,"
            "fallback_used,source_version,source_sha256,source_kind,source_locator,source_job_id,created_by,updated_by,approved_by,"
            "created_at,updated_at,approved_at) VALUES("
            f"{','.join([ph] * 24)})",
            (
                subtitle_id, material_id, group_key, training_area, language, label, "draft", vtt_text, srt_text,
                transcript_text, str(provider or "")[:80], str(model or "")[:160], fallback_value,
                max(1, int(source_version or 1)), str(source_sha256 or "")[:128], str(source_kind or "")[:80],
                str(source_locator or "")[:500], str(source_job_id or "")[:120], actor_username, actor_username, "",
                stamp, stamp, "",
            ),
        )
    return get_subtitle(subtitle_id) or {}


def get_subtitle(subtitle_id: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM media_subtitles WHERE id={ph}", (subtitle_id,)).fetchone()
    return project_subtitle(row)


def get_subtitle_by_source_job_id(source_job_id: str) -> dict | None:
    value = str(source_job_id or "").strip()
    if not value:
        return None
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM media_subtitles WHERE source_job_id={ph} ORDER BY created_at DESC LIMIT 1",
            (value,),
        ).fetchone()
    return project_subtitle(row)


def list_subtitles(material_id: str, limit: int = 30) -> list[dict]:
    safe_limit = max(1, min(100, int(limit)))
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM media_subtitles WHERE material_id={ph} ORDER BY updated_at DESC LIMIT {ph}",
            (material_id, safe_limit),
        ).fetchall()
    return [project_subtitle(row) for row in rows]


def latest_approved(material_id: str, language: str = "") -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        params: list[Any] = [material_id, "approved"]
        sql = f"SELECT * FROM media_subtitles WHERE material_id={ph} AND status={ph}"
        if language:
            sql += f" AND language={ph}"
            params.append(language)
        sql += " ORDER BY approved_at DESC,updated_at DESC LIMIT 1"
        row = conn.execute(sql, tuple(params)).fetchone()
    return project_subtitle(row)


def update_subtitle(subtitle_id: str, *, vtt_text: str, srt_text: str, label: str,
                    status: str, actor_username: str) -> dict | None:
    status = status if status in SUBTITLE_STATUSES else "draft"
    stamp = now()
    approved_by = actor_username if status == "approved" else ""
    approved_at = stamp if status == "approved" else ""
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"UPDATE media_subtitles SET vtt_text={ph},srt_text={ph},label={ph},status={ph},updated_by={ph},updated_at={ph},"
            f"approved_by={ph},approved_at={ph} WHERE id={ph}",
            (vtt_text, srt_text, label, status, actor_username, stamp, approved_by, approved_at, subtitle_id),
        )
        if not int(getattr(cursor, "rowcount", 0) or 0):
            return None
    return get_subtitle(subtitle_id)


__all__ = [
    "ACTIVE_STATUSES", "SUBTITLE_STATUSES", "active_count_for_actor", "claim", "complete", "create_job",
    "create_subtitle", "fail", "get_job", "get_subtitle", "latest_approved", "list_queued", "list_subtitles",
    "now", "project_job", "project_subtitle", "recent_count_for_actor", "requeue_stale_processing", "set_progress",
    "total_active_count", "update_subtitle",
]
