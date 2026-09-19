"""Persistence primitives for asynchronous AI question-generation jobs."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Mapping

from teacher_app.common import db as common_db


ACTIVE_STATUSES = ("queued", "processing")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _decode_json(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def project(row) -> dict | None:
    if row is None:
        return None
    item = dict(row)
    item["request"] = _decode_json(item.pop("request_json", {}))
    item["result"] = _decode_json(item.pop("result_json", {}))
    item["quizCategoryId"] = item.pop("quiz_category_id", "")
    item["group"] = item.pop("group_key", "")
    item["area"] = item.pop("training_area", "")
    item["actorUsername"] = item.pop("actor_username", "")
    item["progressPercent"] = float(item.pop("progress_percent", 0) or 0)
    item["progressStage"] = str(item.pop("progress_stage", "") or "")
    item["progressDetail"] = str(item.pop("progress_detail", "") or "")
    item["claimToken"] = str(item.pop("claim_token", "") or "")
    item["createdAt"] = str(item.pop("created_at", "") or "")
    item["updatedAt"] = str(item.pop("updated_at", "") or "")
    item["startedAt"] = str(item.pop("started_at", "") or "")
    item["completedAt"] = str(item.pop("completed_at", "") or "")
    return item


def create_job(values: Mapping[str, Any]) -> dict:
    stamp = str(values.get("created_at") or now())
    request_json = json.dumps(values.get("request") or {}, ensure_ascii=False)
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        json_expr = f"{ph}::jsonb" if kind == "postgres" else ph
        conn.execute(
            "INSERT INTO ai_question_jobs("
            "id,quiz_category_id,group_key,training_area,actor_username,status,request_json,"
            "progress_percent,progress_stage,progress_detail,result_json,error,claim_token,attempts,"
            "created_at,updated_at,started_at,completed_at) VALUES("
            f"{ph},{ph},{ph},{ph},{ph},{ph},{json_expr},{ph},{ph},{ph},{json_expr},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
            (
                values["id"],
                values["quiz_category_id"],
                values["group_key"],
                values["training_area"],
                values["actor_username"],
                "queued",
                request_json,
                0,
                "等待 AI 出題",
                "工作已排入佇列",
                "{}",
                "",
                "",
                0,
                stamp,
                stamp,
                "",
                "",
            ),
        )
    return get_job(str(values["id"])) or {}


def get_job(job_id: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM ai_question_jobs WHERE id={ph}",
            (job_id,),
        ).fetchone()
    return project(row)


def active_count_for_actor(username: str) -> int:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM ai_question_jobs WHERE actor_username={ph} AND status IN ({ph},{ph})",
            (username, *ACTIVE_STATUSES),
        ).fetchone()
    return int(dict(row).get("n", 0) or 0)


def total_active_count() -> int:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM ai_question_jobs WHERE status IN ({ph},{ph})",
            ACTIVE_STATUSES,
        ).fetchone()
    return int(dict(row).get("n", 0) or 0)


def recent_count_for_actor(username: str, since: str) -> int:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM ai_question_jobs WHERE actor_username={ph} AND created_at>={ph}",
            (username, since),
        ).fetchone()
    return int(dict(row).get("n", 0) or 0)


def claim(job_id: str, claim_token: str) -> dict | None:
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"UPDATE ai_question_jobs SET status={ph},claim_token={ph},attempts=attempts+1,"
            f"started_at={ph},updated_at={ph},progress_stage={ph},progress_detail={ph} "
            f"WHERE id={ph} AND status={ph}",
            (
                "processing",
                claim_token,
                stamp,
                stamp,
                "AI 出題處理中",
                "背景執行器已取得工作",
                job_id,
                "queued",
            ),
        )
        if not int(getattr(cursor, "rowcount", 0) or 0):
            return None
        row = conn.execute(
            f"SELECT * FROM ai_question_jobs WHERE id={ph}",
            (job_id,),
        ).fetchone()
    return project(row)


def set_progress(job_id: str, claim_token: str, percent: float, stage: str, detail: str) -> bool:
    stamp = now()
    percent = max(0.0, min(99.0, float(percent or 0)))
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"UPDATE ai_question_jobs SET progress_percent={ph},progress_stage={ph},progress_detail={ph},updated_at={ph} "
            f"WHERE id={ph} AND status={ph} AND claim_token={ph}",
            (percent, str(stage or "")[:200], str(detail or "")[:1000], stamp, job_id, "processing", claim_token),
        )
    return bool(int(getattr(cursor, "rowcount", 0) or 0))


def complete(job_id: str, claim_token: str, result: Mapping[str, Any]) -> bool:
    stamp = now()
    payload = json.dumps(dict(result), ensure_ascii=False)
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        result_expr = f"{ph}::jsonb" if kind == "postgres" else ph
        cursor = conn.execute(
            f"UPDATE ai_question_jobs SET status={ph},progress_percent={ph},progress_stage={ph},progress_detail={ph},"
            f"result_json={result_expr},error={ph},completed_at={ph},updated_at={ph} "
            f"WHERE id={ph} AND status={ph} AND claim_token={ph}",
            (
                "completed",
                100,
                "AI 候選題完成",
                "候選題已產生，請人工審核後再匯入",
                payload,
                "",
                stamp,
                stamp,
                job_id,
                "processing",
                claim_token,
            ),
        )
    return bool(int(getattr(cursor, "rowcount", 0) or 0))


def fail(job_id: str, claim_token: str, error: str) -> bool:
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"UPDATE ai_question_jobs SET status={ph},progress_percent={ph},progress_stage={ph},progress_detail={ph},"
            f"error={ph},completed_at={ph},updated_at={ph} WHERE id={ph} AND status={ph} AND claim_token={ph}",
            (
                "failed",
                0,
                "AI 出題失敗",
                str(error or "AI 出題失敗")[:1000],
                str(error or "AI 出題失敗")[:2000],
                stamp,
                stamp,
                job_id,
                "processing",
                claim_token,
            ),
        )
    return bool(int(getattr(cursor, "rowcount", 0) or 0))


def list_queued(limit: int = 20) -> list[dict]:
    safe_limit = max(1, min(100, int(limit)))
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM ai_question_jobs WHERE status={ph} ORDER BY created_at ASC LIMIT {ph}",
            ("queued", safe_limit),
        ).fetchall()
    return [project(row) for row in rows]


def requeue_stale_processing(cutoff: str) -> int:
    stamp = now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"UPDATE ai_question_jobs SET status={ph},claim_token={ph},started_at={ph},updated_at={ph},"
            f"progress_percent={ph},progress_stage={ph},progress_detail={ph} "
            f"WHERE status={ph} AND updated_at<{ph}",
            (
                "queued",
                "",
                "",
                stamp,
                0,
                "等待 AI 出題",
                "前一個 Web 執行器已中斷，工作已重新排入佇列",
                "processing",
                cutoff,
            ),
        )
    return int(getattr(cursor, "rowcount", 0) or 0)


__all__ = [
    "ACTIVE_STATUSES",
    "active_count_for_actor",
    "claim",
    "complete",
    "create_job",
    "fail",
    "get_job",
    "list_queued",
    "now",
    "recent_count_for_actor",
    "requeue_stale_processing",
    "set_progress",
    "total_active_count",
]
