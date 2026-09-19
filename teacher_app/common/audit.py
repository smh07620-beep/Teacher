"""Canonical non-PGY audit event persistence and compatibility helpers."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from teacher_app.common import db as common_db
from teacher_app.common.auth import normalize_role


_SECRET_MARKERS = (
    "password",
    "secret",
    "token",
    "authorization",
    "cookie",
    "admin_key",
    "apikey",
    "api_key",
    "session",
)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _secret_key(value: Any) -> bool:
    key = str(value or "").strip().lower()
    return any(marker in key for marker in _SECRET_MARKERS)


def sanitize_audit_payload(value: Any, *, _depth: int = 0) -> Any:
    """Bound structured audit metadata and drop secret-looking fields."""

    if _depth >= 5:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:80]:
            key = str(raw_key or "")[:120]
            if not key or _secret_key(key):
                continue
            out[key] = sanitize_audit_payload(raw_value, _depth=_depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        return [sanitize_audit_payload(item, _depth=_depth + 1) for item in list(value)[:80]]
    return str(value)[:500]


def _json_dump(value: Any) -> str:
    return json.dumps(
        sanitize_audit_payload(value if value is not None else {}),
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _table_exists(conn, kind: str) -> bool:
    if kind == "postgres":
        return bool(
            conn.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=current_schema() AND table_name=%s",
                ("audit_events",),
            ).fetchone()
        )
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            ("audit_events",),
        ).fetchone()
    )


def audit_event_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(row)
    scope = _json_object(item.get("scope_json"))
    return {
        "id": str(item.get("id") or ""),
        "createdAt": str(item.get("created_at") or ""),
        "actorUsername": str(item.get("actor_username") or ""),
        "actorRole": str(item.get("actor_role") or ""),
        "action": str(item.get("action") or ""),
        "targetType": str(item.get("target_type") or ""),
        "targetId": str(item.get("target_id") or ""),
        "group": str(item.get("group_key") or scope.get("group") or ""),
        "scope": scope,
        "before": _json_object(item.get("before_json")),
        "after": _json_object(item.get("after_json")),
        "detail": _json_object(item.get("detail_json")),
        "requestId": str(item.get("request_id") or ""),
    }


def record_event(
    *,
    actor: Mapping[str, Any] | None,
    action: str,
    target_type: str,
    target_id: str = "",
    group: str = "",
    scope: Mapping[str, Any] | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    detail: Mapping[str, Any] | None = None,
    request_id: str = "",
) -> dict[str, Any] | None:
    """Append one bounded audit event.

    Production startup requires migration 0077 before product routes register.
    Standalone compatibility tests may intentionally omit that migration; in
    that narrow case the writer returns ``None`` instead of creating schema at
    runtime.
    """

    actor = actor if isinstance(actor, Mapping) else {}
    username = str(actor.get("username") or "").strip()[:100]
    if not username:
        return None
    action = str(action or "").strip()[:120]
    target_type = str(target_type or "").strip()[:80]
    if not action or not target_type:
        return None
    group = str(group or "").strip()[:100]
    scope_payload = dict(scope or {})
    if group:
        scope_payload.setdefault("group", group)
    event = {
        "id": uuid.uuid4().hex,
        "created_at": utcnow_iso(),
        "actor_username": username,
        "actor_role": normalize_role(actor.get("role", "student")),
        "action": action,
        "target_type": target_type,
        "target_id": str(target_id or "").strip()[:180],
        "group_key": group,
        "scope_json": _json_dump(scope_payload),
        "before_json": _json_dump(before or {}),
        "after_json": _json_dump(after or {}),
        "detail_json": _json_dump(detail or {}),
        "request_id": str(request_id or "").strip()[:120],
    }
    with common_db.transaction() as (conn, kind):
        if not _table_exists(conn, kind):
            return None
        ph = common_db.placeholder(kind)
        columns = list(event)
        conn.execute(
            f"INSERT INTO audit_events ({','.join(columns)}) "
            f"VALUES ({','.join([ph] * len(columns))})",
            tuple(event[column] for column in columns),
        )
    return audit_event_dict(event)


def list_events(
    *,
    limit: int = 200,
    action: str = "",
    target_type: str = "",
    target_id: str = "",
    group: str = "",
) -> list[dict[str, Any]]:
    """Return newest general audit events with bounded optional filters."""

    limit = max(1, min(500, int(limit or 200)))
    with common_db.read_connection() as (conn, kind):
        if not _table_exists(conn, kind):
            return []
        ph = common_db.placeholder(kind)
        clauses: list[str] = []
        params: list[Any] = []
        for column, value, maximum in (
            ("action", action, 120),
            ("target_type", target_type, 80),
            ("target_id", target_id, 180),
            ("group_key", group, 100),
        ):
            clean = str(value or "").strip()[:maximum]
            if clean:
                clauses.append(f"{column}={ph}")
                params.append(clean)
        sql = "SELECT * FROM audit_events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += f" ORDER BY created_at DESC LIMIT {limit}"
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [audit_event_dict(dict(row)) for row in rows]


def build_audit_event(
    *,
    assignment_id: str,
    actor_username: str,
    action: str,
    from_status: str,
    to_status: str,
    detail: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "assignment_id": assignment_id,
        "actor_username": actor_username,
        "action": action,
        "from_status": from_status,
        "to_status": to_status,
        "detail": detail or {},
        "created_at": utcnow_iso(),
    }
