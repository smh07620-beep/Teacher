"""Read-only aggregation for Teacher 7.1 Training Command Center.

PGY learner content is opt-in through the explicit admin-managed audience flag.
Online/course/exam tasks are composed by the frontend from existing canonical
read APIs; no mutation workflow is duplicated here.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Optional

from teacher_app.command_center import audience
from teacher_app.common.auth import normalize_role
from teacher_app.common.errors import ApiError
from teacher_app.pgy import service as pgy_service


ACTIONABLE_PGY = {
    "student": {
        "assigned": ("submit", "填寫並送出"),
    },
    "clinical_teacher": {
        "submitted": ("teacher_sign", "教師簽核"),
    },
    "group_leader": {
        "teacher_signed": ("group_countersign", "組長複核"),
    },
    "education_admin": {
        "group_countersigned": ("finalize", "最終確認"),
    },
}

STATUS_LABELS = {
    "assigned": "待學員完成",
    "submitted": "待教師簽核",
    "teacher_signed": "待組長複核",
    "group_countersigned": "待最終確認",
}


def _parse_datetime(value: Any) -> Optional[dt.datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _is_overdue(value: Any, now: dt.datetime) -> bool:
    due = _parse_datetime(value)
    return bool(due and due < now)


def _task_sort_key(item: Mapping[str, Any]):
    due = _parse_datetime(item.get("dueAt"))
    return (
        0 if item.get("overdue") else 1,
        due or dt.datetime.max.replace(tzinfo=dt.timezone.utc),
        str(item.get("title") or ""),
    )


def build_summary(
    user: Optional[Mapping[str, Any]],
    *,
    now: Optional[dt.datetime] = None,
) -> dict[str, Any]:
    """Return one authenticated user's read-only command-center projection."""
    if not user:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入後再查看待辦。",
            status=401,
            extra={"loginRequired": True},
        )

    profile = audience.current_profile(user)
    role = normalize_role(user.get("role", "student"))
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)

    # Fail closed: a normal/online user never receives PGY workflow content,
    # even if stale PGY rows happen to exist for the same account.
    actionable = ACTIONABLE_PGY.get(role, {}) if profile["pgyLearner"] else {}
    assignments = pgy_service.list_assignments(user) if actionable else []
    items: list[dict[str, Any]] = []

    for assignment in assignments:
        status = str(assignment.get("status") or "")
        action_spec = actionable.get(status)
        if not action_spec:
            continue
        action, action_label = action_spec
        due_at = str(assignment.get("dueAt") or "")
        items.append(
            {
                "id": str(assignment.get("id") or ""),
                "domain": "pgy",
                "kind": "assignment",
                "title": str(assignment.get("title") or "PGY 訓練指派"),
                "status": status,
                "statusLabel": STATUS_LABELS.get(status, status),
                "group": str(assignment.get("group") or ""),
                "dueAt": due_at,
                "overdue": _is_overdue(due_at, current),
                "action": action,
                "actionLabel": action_label,
                "target": "pgy-workflow",
            }
        )

    items.sort(key=_task_sort_key)
    overdue = sum(1 for item in items if item["overdue"])
    return {
        "role": role,
        "audience": profile["audience"],
        "pgyLearner": profile["pgyLearner"],
        "scope": ["online", "pgy"] if profile["pgyLearner"] else ["online"],
        "generatedAt": current.isoformat(),
        "counts": {
            "total": len(items),
            "overdue": overdue,
            "pgy": len(items),
        },
        "items": items,
    }
