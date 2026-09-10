"""Audit event helpers. Persistence stays in legacy PGY modules for now."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
