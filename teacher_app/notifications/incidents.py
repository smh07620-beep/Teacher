"""Persistent lifecycle for de-duplicated operational incidents."""
from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Any, Iterable, Mapping

from teacher_app.common import db as common_db
from teacher_app.worker import operations as worker_operations


LOGGER = logging.getLogger(__name__)
_AI_QUEUE_SPECS = (
    ("question", "ai_question_jobs", "AI 出題", "AI_QUESTION_FAILURE_BURST"),
    ("script", "media_script_jobs", "AI 教材／講稿", "AI_SCRIPT_FAILURE_BURST"),
    ("audio", "media_audio_jobs", "AI 語音", "AI_AUDIO_FAILURE_BURST"),
    ("subtitle", "media_subtitle_jobs", "AI 字幕", "AI_SUBTITLE_FAILURE_BURST"),
    ("presentation", "ai_presentation_jobs", "AI 投影片", "AI_PRESENTATION_FAILURE_BURST"),
    ("video", "ai_video_jobs", "AI 影片", "AI_VIDEO_FAILURE_BURST"),
)


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _missing_relation(exc: BaseException) -> bool:
    text = str(exc or "").lower()
    return "no such table" in text or ("relation" in text and "does not exist" in text)


def _ai_job_incident_candidates() -> list[dict[str, Any]]:
    """Project sustained AI queue failures without exposing provider error text."""
    threshold = _int_env("AI_INCIDENT_CONSECUTIVE_FAILURES", 2, 2, 10)
    sample_limit = max(6, threshold + 2)
    candidates: list[dict[str, Any]] = []
    for queue_key, table, label, error_code in _AI_QUEUE_SPECS:
        try:
            with common_db.read_connection() as (conn, kind):
                ph = common_db.placeholder(kind)
                rows = conn.execute(
                    f"SELECT id,status,updated_at FROM {table} "
                    f"WHERE status IN ({ph},{ph}) "
                    f"ORDER BY updated_at DESC,id DESC LIMIT {ph}",
                    ("failed", "completed", sample_limit),
                ).fetchall()
        except Exception as exc:
            if _missing_relation(exc):
                # Mixed-version fixtures may not have every optional AI queue yet.
                continue
            LOGGER.warning(
                "operational incident AI projection failed queue=%s error_type=%s",
                queue_key,
                type(exc).__name__,
            )
            raise

        consecutive_failures = 0
        for row in rows:
            status = str(dict(row).get("status") or "")
            if status == "completed":
                break
            if status == "failed":
                consecutive_failures += 1
            else:
                break
        if consecutive_failures < threshold:
            continue
        candidates.append({
            "incidentKey": f"ai_queue_failure:{queue_key}",
            "incidentType": "ai_queue_failure",
            "category": "ai",
            "severity": "critical" if consecutive_failures >= threshold + 1 else "warning",
            "title": f"{label}背景工作連續失敗",
            "detail": f"最近已連續 {consecutive_failures} 筆{label}背景工作失敗。",
            "action": "查看 AI Worker、provider 額度／可用性與工作技術狀態；修復後可使用原工作安全重試。",
            "errorCode": error_code,
            "resourceId": queue_key,
        })
    return candidates


def _now(value: dt.datetime | None = None) -> dt.datetime:
    current = value or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    return current.astimezone(dt.timezone.utc)


def incident_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    return {
        "incidentKey": str(item.get("incident_key") or item.get("incidentKey") or ""),
        "incidentType": str(item.get("incident_type") or item.get("incidentType") or ""),
        "category": str(item.get("category") or "operations"),
        "severity": str(item.get("severity") or "warning"),
        "status": str(item.get("status") or "open"),
        "title": str(item.get("title") or "系統維運事件"),
        "detail": str(item.get("detail") or ""),
        "action": str(item.get("action") or ""),
        "errorCode": str(item.get("error_code") or item.get("errorCode") or ""),
        "resourceId": str(item.get("resource_id") or item.get("resourceId") or ""),
        "generation": int(item.get("generation") or 1),
        "occurrenceCount": int(item.get("occurrence_count") or item.get("occurrenceCount") or 1),
        "openedAt": str(item.get("opened_at") or item.get("openedAt") or ""),
        "lastSeenAt": str(item.get("last_seen_at") or item.get("lastSeenAt") or ""),
        "resolvedAt": str(item.get("resolved_at") or item.get("resolvedAt") or ""),
    }


def _normalize_candidate(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    key = str(raw.get("incidentKey") or "").strip()[:240]
    incident_type = str(raw.get("incidentType") or "").strip()[:80]
    title = str(raw.get("title") or "").strip()[:240]
    if not key or not incident_type or not title:
        return None
    return {
        "incident_key": key,
        "incident_type": incident_type,
        "category": str(raw.get("category") or "operations").strip()[:80],
        "severity": str(raw.get("severity") or "warning").strip()[:32],
        "title": title,
        "detail": str(raw.get("detail") or "").strip()[:1200],
        "action": str(raw.get("action") or "").strip()[:1200],
        "error_code": str(raw.get("errorCode") or "").strip()[:120],
        "resource_id": str(raw.get("resourceId") or "").strip()[:240],
    }


def sync_operational_incidents(
    *,
    now: dt.datetime | None = None,
    candidates: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Open, refresh, reopen, and resolve incidents without duplicate rows."""
    current = _now(now)
    stamp = current.isoformat()
    explicit_candidates = candidates is not None
    if explicit_candidates:
        raw_candidates = list(candidates)
    else:
        raw_candidates = worker_operations.operational_incident_candidates(now=current)
        raw_candidates.extend(_ai_job_incident_candidates())
    confirmed_worker_recoveries = (
        set()
        if explicit_candidates
        else worker_operations.online_worker_recovery_keys(now=current)
    )
    active: dict[str, dict[str, Any]] = {}
    for raw in raw_candidates:
        normalized = _normalize_candidate(raw)
        if normalized:
            active[normalized["incident_key"]] = normalized

    opened: list[dict[str, Any]] = []
    reopened: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []

    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        try:
            rows = conn.execute("SELECT * FROM operational_incidents").fetchall()
        except Exception as exc:
            # Mixed-version safety: production requires 0108, but isolated old
            # fixtures must not create schema at runtime.
            LOGGER.warning(
                "operational incident persistence unavailable error_type=%s",
                type(exc).__name__,
            )
            return {"opened": [], "reopened": [], "resolved": [], "active": []}
        existing = {
            str(dict(row).get("incident_key") or ""): dict(row)
            for row in rows
        }

        for key, candidate in active.items():
            prior = existing.get(key)
            if prior is None:
                columns = [
                    "incident_key", "incident_type", "category", "severity", "status",
                    "title", "detail", "action", "error_code", "resource_id",
                    "generation", "occurrence_count", "opened_at", "last_seen_at", "resolved_at",
                ]
                values = [
                    candidate["incident_key"], candidate["incident_type"], candidate["category"],
                    candidate["severity"], "open", candidate["title"], candidate["detail"],
                    candidate["action"], candidate["error_code"], candidate["resource_id"],
                    1, 1, stamp, stamp, "",
                ]
                conn.execute(
                    f"INSERT INTO operational_incidents({','.join(columns)}) "
                    f"VALUES ({','.join([ph] * len(columns))})",
                    tuple(values),
                )
                opened.append(incident_dict(dict(zip(columns, values))))
                continue

            if str(prior.get("status") or "") == "open":
                conn.execute(
                    f"UPDATE operational_incidents SET "
                    f"incident_type={ph},category={ph},severity={ph},title={ph},detail={ph},"
                    f"action={ph},error_code={ph},resource_id={ph},last_seen_at={ph} "
                    f"WHERE incident_key={ph}",
                    (
                        candidate["incident_type"], candidate["category"], candidate["severity"],
                        candidate["title"], candidate["detail"], candidate["action"],
                        candidate["error_code"], candidate["resource_id"], stamp, key,
                    ),
                )
                continue

            generation = int(prior.get("generation") or 1) + 1
            occurrence_count = int(prior.get("occurrence_count") or 1) + 1
            conn.execute(
                f"UPDATE operational_incidents SET "
                f"incident_type={ph},category={ph},severity={ph},status={ph},title={ph},detail={ph},"
                f"action={ph},error_code={ph},resource_id={ph},generation={ph},occurrence_count={ph},"
                f"opened_at={ph},last_seen_at={ph},resolved_at={ph} WHERE incident_key={ph}",
                (
                    candidate["incident_type"], candidate["category"], candidate["severity"], "open",
                    candidate["title"], candidate["detail"], candidate["action"],
                    candidate["error_code"], candidate["resource_id"], generation,
                    occurrence_count, stamp, stamp, "", key,
                ),
            )
            reopened.append(
                incident_dict({
                    **prior,
                    **candidate,
                    "status": "open",
                    "generation": generation,
                    "occurrence_count": occurrence_count,
                    "opened_at": stamp,
                    "last_seen_at": stamp,
                    "resolved_at": "",
                })
            )

        for key, prior in existing.items():
            if str(prior.get("status") or "") != "open" or key in active:
                continue
            if (
                not explicit_candidates
                and str(prior.get("incident_type") or "") == "worker_offline"
            ):
                identity = key.split(":", 1)[1].strip().lower() if ":" in key else ""
                if not identity or identity not in confirmed_worker_recoveries:
                    # Absence from the retained heartbeat list is not proof of
                    # recovery. Only a fresh heartbeat closes Worker outages.
                    continue
            conn.execute(
                f"UPDATE operational_incidents SET status={ph},resolved_at={ph},last_seen_at={ph} "
                f"WHERE incident_key={ph} AND status={ph}",
                ("resolved", stamp, stamp, key, "open"),
            )
            resolved.append(
                incident_dict({
                    **prior,
                    "status": "resolved",
                    "resolved_at": stamp,
                    "last_seen_at": stamp,
                })
            )

    return {
        "opened": opened,
        "reopened": reopened,
        "resolved": resolved,
        "active": list_active_incidents(),
    }


def list_active_incidents() -> list[dict[str, Any]]:
    try:
        with common_db.read_connection() as (conn, _kind):
            rows = conn.execute(
                "SELECT * FROM operational_incidents WHERE status='open' "
                "ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,"
                "last_seen_at DESC"
            ).fetchall()
    except Exception as exc:
        LOGGER.warning(
            "operational incident read failed view=active error_type=%s",
            type(exc).__name__,
        )
        return []
    return [incident_dict(dict(row)) for row in rows]


def list_recent_incidents(
    *,
    now: dt.datetime | None = None,
    resolved_hours: int = 24,
) -> list[dict[str, Any]]:
    current = _now(now)
    cutoff = (current - dt.timedelta(hours=max(1, min(168, int(resolved_hours))))).isoformat()
    try:
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            rows = conn.execute(
                f"SELECT * FROM operational_incidents "
                f"WHERE status='open' OR (status='resolved' AND resolved_at>={ph}) "
                f"ORDER BY CASE WHEN status='open' THEN 0 ELSE 1 END,"
                f"CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,"
                f"last_seen_at DESC",
                (cutoff,),
            ).fetchall()
    except Exception as exc:
        LOGGER.warning(
            "operational incident read failed view=recent error_type=%s",
            type(exc).__name__,
        )
        return []
    return [incident_dict(dict(row)) for row in rows]


__all__ = [
    "incident_dict",
    "list_active_incidents",
    "list_recent_incidents",
    "sync_operational_incidents",
]
