"""Canonical actionable notification events shared by in-app and email channels.

Business state remains owned by Training Command Center, dashboard completion rules,
exam windows, Worker jobs, and assessment records.  This module only projects those
already-authorized facts into stable notification events.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any, Mapping, Optional

from teacher_app.command_center import dashboard_service, service
from teacher_app.common.errors import ApiError
from teacher_app.exams import windows as exam_windows


EMAIL_ONCE_KINDS = {"retraining", "review", "material_failure"}
EMAIL_DUE_KINDS = {"course", "exam", "due"}


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


def _stable_key(*parts: Any) -> str:
    raw = "\x1f".join(str(part or "") for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"notify:{str(parts[0] or 'event')}:{digest}"[:240]


def _href(item: Mapping[str, Any]) -> str:
    area = str(item.get("area") or "internal")
    group = str(item.get("group") or "grpBio")
    target = str(item.get("target") or "")
    resource_id = str(item.get("resourceId") or item.get("id") or "")
    course_id = str(item.get("courseId") or "")
    if target == "pgy-workflow":
        return f"/system?area=pgy&group={group or 'grpNew'}&module=assessment&from=notification-center"
    if target == "exam" or item.get("kind") == "exam":
        suffix = f"&examId={resource_id}" if resource_id else ""
        return f"/system?area={area}&group={group}&module=exam&from=notification-center{suffix}"
    if target == "assessment" or item.get("kind") == "review":
        suffix = f"&recordId={resource_id}" if resource_id else ""
        return f"/system?area={area}&group={group}&module=exam&from=notification-center{suffix}"
    if target == "course-materials" or item.get("persona") == "teacher":
        suffix = f"&courseId={course_id or resource_id}" if (course_id or resource_id) else ""
        return f"/system?area={area}&group={group}&admin=1&workspace=course-materials&persona=teacher&from=notification-center{suffix}"
    suffix = f"&courseId={course_id}" if course_id else ""
    if item.get("kind") in {"material", "retraining"} and resource_id:
        suffix += f"&materialId={resource_id}"
    return f"/system?area={area}&group={group}&module=materials&from=notification-center{suffix}"


def _badge(kind: str, overdue: bool, status: str) -> str:
    if overdue:
        return "逾期"
    return {
        "course": "必修課程",
        "exam": "補強再測" if status == "remediation" else "考核",
        "retraining": "重新訓練",
        "review": "待批改",
        "material_failure": "教材需處理",
        "due": "即將到期",
        "draft": "草稿",
        "material": "教材",
    }.get(kind, "待辦")


def _event(item: Mapping[str, Any]) -> dict[str, Any]:
    kind = str(item.get("kind") or "task")
    due_at = str(item.get("dueAt") or "")
    status = str(item.get("status") or "")
    resource_id = str(item.get("resourceId") or item.get("id") or "")
    key = _stable_key(kind, item.get("persona"), resource_id, item.get("courseId"), status, due_at)
    email_policy = "once" if kind in EMAIL_ONCE_KINDS else "due" if kind in EMAIL_DUE_KINDS else "none"
    return {
        "key": key,
        "persona": str(item.get("persona") or "learner"),
        "kind": kind,
        "domain": str(item.get("domain") or "learning"),
        "title": str(item.get("title") or "待處理項目"),
        "detail": str(item.get("detail") or item.get("statusLabel") or "等待處理"),
        "badge": _badge(kind, bool(item.get("overdue")), status),
        "status": status,
        "overdue": bool(item.get("overdue")),
        "dueAt": due_at,
        "area": str(item.get("area") or "internal"),
        "group": str(item.get("group") or ""),
        "resourceId": resource_id,
        "courseId": str(item.get("courseId") or ""),
        "sourceRetained": bool(item.get("sourceRetained")),
        "href": _href(item),
        "channels": ["in_app"] + (["email"] if email_policy != "none" else []),
        "emailPolicy": email_policy,
    }


def _exam_deadline_events(user: Mapping[str, Any], current: dt.datetime) -> list[dict[str, Any]]:
    """Add server-authoritative exam deadlines without reimplementing completion rules."""
    try:
        dashboard = dashboard_service.dashboard_summary(user, now=current)
    except Exception:
        return []
    values: list[dict[str, Any]] = []
    for exam in dashboard.get("pendingExams") or []:
        exam_id = str(exam.get("id") or "")
        if not exam_id:
            continue
        try:
            window = exam_windows.get_window(exam_id) or {}
        except Exception:
            continue
        enabled = window.get("reminder_enabled", window.get("reminderEnabled", True))
        if enabled in (False, 0, "0", "false", "False"):
            continue
        due = _parse_datetime(window.get("closes_at") or window.get("closesAt"))
        if not due:
            continue
        item = {
            "id": exam_id,
            "resourceId": exam_id,
            "courseId": str(exam.get("courseId") or ""),
            "persona": "learner",
            "domain": "assessment",
            "kind": "exam",
            "title": str(exam.get("title") or "待完成考核"),
            "status": "remediation" if exam.get("remediationRequired") else "pending",
            "statusLabel": "補強再測" if exam.get("remediationRequired") else "待完成考核",
            "group": str(exam.get("group") or ""),
            "area": str(exam.get("area") or "internal"),
            "dueAt": due.isoformat(),
            "overdue": due < current,
            "detail": ("考核已超過最後作答時間" if due < current else "考核已設定最後作答時間"),
            "target": "exam",
        }
        values.append(_event(item))
    return values


def build_events(user: Optional[Mapping[str, Any]], *, now: Optional[dt.datetime] = None) -> dict[str, Any]:
    if not user:
        raise ApiError("LOGIN_REQUIRED", "請先登入後再查看通知。", status=401, extra={"loginRequired": True})
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)
    command = service.build_summary(user, now=current)
    events = [_event(item) for item in command.get("items") or []]

    # Command-center intentionally de-duplicates exams covered by a course.  A
    # deadline remains independently important for notification/email purposes,
    # so merge the canonical exam-window deadline here by stable resource id.
    deadline_events = _exam_deadline_events(user, current)
    by_identity = {(row["kind"], row["persona"], row["resourceId"]): row for row in events}
    for row in deadline_events:
        identity = (row["kind"], row["persona"], row["resourceId"])
        existing = by_identity.get(identity)
        if existing:
            existing.update({"dueAt": row["dueAt"], "overdue": row["overdue"], "emailPolicy": "due"})
            existing["channels"] = ["in_app", "email"]
            existing["key"] = row["key"]
            if row["overdue"]:
                existing["badge"] = "逾期"
        else:
            events.append(row)
            by_identity[identity] = row

    events.sort(key=lambda row: (
        0 if row.get("overdue") else 1,
        0 if row.get("kind") in {"review", "material_failure"} else 1,
        _parse_datetime(row.get("dueAt")) or dt.datetime.max.replace(tzinfo=dt.timezone.utc),
        str(row.get("title") or ""),
    ))
    return {
        "items": events,
        "counts": {
            "total": len(events),
            "overdue": sum(1 for row in events if row.get("overdue")),
            "emailEligible": sum(1 for row in events if "email" in row.get("channels", [])),
        },
        "source": "training-command-center",
    }


def email_events(user: Mapping[str, Any], *, now: Optional[dt.datetime] = None, days: int = 3) -> list[dict[str, Any]]:
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)
    horizon = current + dt.timedelta(days=max(1, int(days)))
    output = []
    for event in build_events(user, now=current)["items"]:
        if "email" not in event.get("channels", []):
            continue
        policy = event.get("emailPolicy")
        if policy == "once":
            output.append(event)
            continue
        due = _parse_datetime(event.get("dueAt"))
        if policy == "due" and due and due <= horizon:
            output.append(event)
    return output


__all__ = ["build_events", "email_events"]
