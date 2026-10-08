"""Persistence for teacher AI material-generation jobs and reviewed drafts."""
from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any, Mapping

from teacher_app.common import db as common_db


ACTIVE_STATUSES = ("queued", "processing")
SCRIPT_STATUSES = {"draft", "approved"}
DRAFT_TYPES = {"handout", "summary", "slides", "script", "quiz", "objectives"}


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


def project_script(row) -> dict | None:
    if row is None:
        return None
    item = dict(row)
    item["materialId"] = item.pop("material_id", "")
    item["group"] = item.pop("group_key", "")
    item["area"] = item.pop("training_area", "")
    item["sourceJobId"] = item.pop("source_job_id", "")
    item["sourceChunks"] = _decode(item.pop("source_chunks_json", []), [])
    item["draftType"] = str(item.pop("draft_type", "script") or "script")
    item["provider"] = str(item.pop("provider", "") or "")
    item["model"] = str(item.pop("model", "") or "")
    item["fallbackUsed"] = bool(item.pop("fallback_used", False))
    item["publicationMaterialId"] = str(item.pop("publication_material_id", "") or "")
    item["createdBy"] = item.pop("created_by", "")
    item["updatedBy"] = item.pop("updated_by", "")
    item["approvedBy"] = item.pop("approved_by", "")
    item["createdAt"] = item.pop("created_at", "")
    item["updatedAt"] = item.pop("updated_at", "")
    item["approvedAt"] = item.pop("approved_at", "")
    return item


def create_job(values: Mapping[str, Any]) -> dict:
    stamp = str(values.get("created_at") or now())
    request_json = json.dumps(values.get("request") or {}, ensure_ascii=False)
    output_type = str((values.get("request") or {}).get("outputType") or "script")
    stage = "等待產生講稿" if output_type == "script" else "等待 AI 教材草稿"
    detail = "工作已排入 AI 佇列"
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        json_expr = f"{ph}::jsonb" if kind == "postgres" else ph
        conn.execute(
            "INSERT INTO media_script_jobs("
            "id,material_id,group_key,training_area,actor_username,status,request_json,"
            "progress_percent,progress_stage,progress_detail,result_json,error,claim_token,attempts,"
            "created_at,updated_at,started_at,completed_at) VALUES("
            f"{ph},{ph},{ph},{ph},{ph},{ph},{json_expr},{ph},{ph},{ph},{json_expr},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
            (
                values["id"], values["material_id"], values["group_key"], values["training_area"],
                values["actor_username"], "queued", request_json, 0, stage, detail,
                "{}", "", "", 0, stamp, stamp, "", "",
            ),
        )
    return get_job(str(values["id"])) or {}


def get_job(job_id: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM media_script_jobs WHERE id={ph}", (job_id,)).fetchone()
    return project_job(row)


def active_count_for_actor(username: str) -> int:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM media_script_jobs WHERE actor_username={ph} AND status IN ({ph},{ph})",
            (username, *ACTIVE_STATUSES),
        ).fetchone()
    return int(dict(row).get("n", 0) or 0)


def total_active_count() -> int:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM media_script_jobs WHERE status IN ({ph},{ph})", ACTIVE_STATUSES
        ).fetchone()
    return int(dict(row).get("n", 0) or 0)


def recent_count_for_actor(username: str, since: str) -> int:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM media_script_jobs WHERE actor_username={ph} AND created_at>={ph}",
            (username, since),
        ).fetchone()
    return int(dict(row).get("n", 0) or 0)


def claim(job_id: str, token: str) -> dict | None:
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"UPDATE media_script_jobs SET status={ph},claim_token={ph},attempts=attempts+1,started_at={ph},updated_at={ph},"
            f"progress_stage={ph},progress_detail={ph} WHERE id={ph} AND status={ph}",
            ("processing", token, stamp, stamp, "AI 教材處理中", "AI Worker 已取得工作", job_id, "queued"),
        )
        if not int(getattr(cursor, "rowcount", 0) or 0):
            return None
        row = conn.execute(f"SELECT * FROM media_script_jobs WHERE id={ph}", (job_id,)).fetchone()
    return project_job(row)


def set_progress(job_id: str, token: str, percent: float, stage: str, detail: str) -> bool:
    stamp = now()
    percent = max(0.0, min(99.0, float(percent or 0)))
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"UPDATE media_script_jobs SET progress_percent={ph},progress_stage={ph},progress_detail={ph},updated_at={ph} "
            f"WHERE id={ph} AND status={ph} AND claim_token={ph}",
            (percent, str(stage or "")[:200], str(detail or "")[:1000], stamp, job_id, "processing", token),
        )
    return bool(int(getattr(cursor, "rowcount", 0) or 0))


def complete(job_id: str, token: str, result: Mapping[str, Any]) -> bool:
    stamp = now()
    payload = json.dumps(dict(result), ensure_ascii=False)
    label = str(result.get("outputLabel") or "AI 教材草稿")
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        result_expr = f"{ph}::jsonb" if kind == "postgres" else ph
        cursor = conn.execute(
            f"UPDATE media_script_jobs SET status={ph},progress_percent={ph},progress_stage={ph},progress_detail={ph},"
            f"result_json={result_expr},error={ph},completed_at={ph},updated_at={ph} "
            f"WHERE id={ph} AND status={ph} AND claim_token={ph}",
            ("completed", 100, f"{label}完成", "請由老師確認、編修並核准後再發布", payload, "", stamp, stamp, job_id, "processing", token),
        )
    return bool(int(getattr(cursor, "rowcount", 0) or 0))


def fail(job_id: str, token: str, error: str) -> bool:
    stamp = now()
    message = str(error or "AI 教材草稿產生失敗")[:2000]
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"UPDATE media_script_jobs SET status={ph},progress_percent={ph},progress_stage={ph},progress_detail={ph},error={ph},"
            f"completed_at={ph},updated_at={ph} WHERE id={ph} AND status={ph} AND claim_token={ph}",
            ("failed", 0, "AI 教材產生失敗", message[:1000], message, stamp, stamp, job_id, "processing", token),
        )
    return bool(int(getattr(cursor, "rowcount", 0) or 0))


def list_queued(limit: int = 20) -> list[dict]:
    safe_limit = max(1, min(100, int(limit)))
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM media_script_jobs WHERE status={ph} ORDER BY created_at ASC LIMIT {ph}",
            ("queued", safe_limit),
        ).fetchall()
    return [project_job(row) for row in rows]


def requeue_stale_processing(cutoff: str) -> int:
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"UPDATE media_script_jobs SET status={ph},claim_token={ph},started_at={ph},updated_at={ph},progress_percent={ph},"
            f"progress_stage={ph},progress_detail={ph} WHERE status={ph} AND updated_at<{ph}",
            ("queued", "", "", stamp, 0, "等待 AI 教材草稿", "前一個 AI Worker 已中斷，工作已重新排入佇列", "processing", cutoff),
        )
    return int(getattr(cursor, "rowcount", 0) or 0)


def create_script(*, material_id: str, group_key: str, training_area: str, title: str, body: str,
                  source_job_id: str, source_chunks: list, actor_username: str,
                  draft_type: str = "script", provider: str = "", model: str = "",
                  fallback_used: bool = False, publication_material_id: str = "") -> dict:
    draft_type = str(draft_type or "script").strip().lower()
    if draft_type not in DRAFT_TYPES:
        raise ValueError("不支援的 AI 教材草稿類型")
    script_id = f"mscript-{uuid.uuid4().hex}"
    stamp = now()
    chunks = json.dumps(source_chunks or [], ensure_ascii=False)
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        chunks_expr = f"{ph}::jsonb" if kind == "postgres" else ph
        fallback_value = bool(fallback_used) if kind == "postgres" else int(bool(fallback_used))
        conn.execute(
            "INSERT INTO media_scripts(id,material_id,group_key,training_area,title,body,status,source_job_id,source_chunks_json,"
            "draft_type,provider,model,fallback_used,publication_material_id,created_by,updated_by,approved_by,created_at,updated_at,approved_at) VALUES("
            f"{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{chunks_expr},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
            (
                script_id, material_id, group_key, training_area, title, body, "draft", source_job_id, chunks,
                draft_type, str(provider or "")[:80], str(model or "")[:160], fallback_value,
                str(publication_material_id or "")[:120], actor_username, actor_username, "", stamp, stamp, "",
            ),
        )
    return get_script(script_id) or {}


def get_script(script_id: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM media_scripts WHERE id={ph}", (script_id,)).fetchone()
    return project_script(row)


def list_scripts(material_id: str, limit: int = 30) -> list[dict]:
    """Return only real lecture scripts so narration cannot see other AI drafts."""
    safe_limit = max(1, min(100, int(limit)))
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM media_scripts WHERE material_id={ph} AND draft_type={ph} ORDER BY updated_at DESC LIMIT {ph}",
            (material_id, "script", safe_limit),
        ).fetchall()
    return [project_script(row) for row in rows]


def list_drafts(material_id: str, limit: int = 50) -> list[dict]:
    safe_limit = max(1, min(100, int(limit)))
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM media_scripts WHERE material_id={ph} ORDER BY updated_at DESC LIMIT {ph}",
            (material_id, safe_limit),
        ).fetchall()
    return [project_script(row) for row in rows]


def update_script(script_id: str, *, title: str, body: str, status: str, actor_username: str,
                  publication_material_id: str | None = None) -> dict | None:
    status = status if status in SCRIPT_STATUSES else "draft"
    stamp = now()
    approved_by = actor_username if status == "approved" else ""
    approved_at = stamp if status == "approved" else ""
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        fields = [
            f"title={ph}", f"body={ph}", f"status={ph}", f"updated_by={ph}", f"updated_at={ph}",
            f"approved_by={ph}", f"approved_at={ph}",
        ]
        params: list[Any] = [title, body, status, actor_username, stamp, approved_by, approved_at]
        if publication_material_id is not None:
            fields.append(f"publication_material_id={ph}")
            params.append(str(publication_material_id or "")[:120])
        params.append(script_id)
        cursor = conn.execute(
            f"UPDATE media_scripts SET {','.join(fields)} WHERE id={ph}",
            tuple(params),
        )
        if not int(getattr(cursor, "rowcount", 0) or 0):
            return None
    return get_script(script_id)


def delete_script(script_id: str) -> bool:
    """Permanently discard one AI draft/script row (teacher abandoned it)."""
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(f"DELETE FROM media_scripts WHERE id={ph}", (script_id,))
        return bool(int(getattr(cursor, "rowcount", 0) or 0))


__all__ = [
    "ACTIVE_STATUSES", "DRAFT_TYPES", "SCRIPT_STATUSES", "active_count_for_actor", "claim", "complete", "create_job",
    "create_script", "delete_script", "fail", "get_job", "get_script", "list_drafts", "list_queued", "list_scripts", "now",
    "recent_count_for_actor", "requeue_stale_processing", "set_progress", "total_active_count", "update_script",
]
