"""Canonical actionable notification events shared by in-app and email channels.

Business state remains owned by Training Command Center, dashboard completion rules,
exam windows, Worker jobs, and assessment records.  This module only projects those
already-authorized facts into stable notification events.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
from typing import Any, Mapping, Optional

from teacher_app.command_center import dashboard_service, service
from teacher_app.common.auth import has_role
from teacher_app.worker import operations as worker_operations
from teacher_app.notifications import incidents
from teacher_app.common.errors import ApiError
from teacher_app.exams import windows as exam_windows


LOGGER = logging.getLogger(__name__)


EMAIL_ONCE_KINDS = {"retraining", "review", "material_failure", "worker_offline", "operational_incident", "operational_recovery"}
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
    if target == "worker" or item.get("kind") in {"worker_offline", "operational_incident", "operational_recovery"}:
        return "/system?admin=1&workspace=worker&persona=system&from=notification-center"
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
    material_id = str(item.get("materialId") or "")
    if material_id:
        suffix += f"&materialId={material_id}"
    elif item.get("kind") in {"material", "retraining"} and resource_id:
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
        "intervention": "教師追蹤",
        "worker_offline": "Worker 離線",
        "operational_incident": "系統事件",
        "operational_recovery": "已恢復",
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
        "incidentType": str(item.get("incidentType") or ""),
        "severity": str(item.get("severity") or ""),
        "errorCode": str(item.get("errorCode") or ""),
        "action": str(item.get("action") or ""),
        "generation": int(item.get("generation") or 0),
        "responseState": str(item.get("responseState") or ""),
        "assignedTo": str(item.get("assignedTo") or ""),
        "maintenanceActive": bool(item.get("maintenanceActive")),
        "maintenanceUntil": str(item.get("maintenanceUntil") or ""),
    }


def _exam_deadline_events(user: Mapping[str, Any], current: dt.datetime) -> list[dict[str, Any]]:
    """Add server-authoritative exam deadlines without reimplementing completion rules."""
    try:
        dashboard = dashboard_service.dashboard_summary(user, now=current)
    except Exception as exc:
        LOGGER.warning(
            "notification exam deadline projection failed error_type=%s",
            type(exc).__name__,
        )
        return []
    values: list[dict[str, Any]] = []
    for exam in dashboard.get("pendingExams") or []:
        exam_id = str(exam.get("id") or "")
        if not exam_id:
            continue
        try:
            window = exam_windows.get_window(exam_id) or {}
        except Exception as exc:
            LOGGER.warning(
                "notification exam window lookup failed exam_id=%s error_type=%s",
                exam_id[:100],
                type(exc).__name__,
            )
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


def _worker_offline_events(
    user: Mapping[str, Any],
    current: dt.datetime,
) -> list[dict[str, Any]]:
    if not has_role(user, "system_admin"):
        return []
    status = worker_operations.offline_worker_alerts(now=current)
    if not status.get("available"):
        return []
    threshold_minutes = max(1, int(status.get("thresholdSeconds") or 0) // 60)
    output = []
    for worker in status.get("workers") or []:
        worker_id = str(worker.get("workerId") or "").strip()
        last_seen = str(worker.get("lastSeen") or "").strip()
        if not worker_id or not last_seen:
            continue
        offline_minutes = max(1, int(worker.get("offlineSeconds") or 0) // 60)
        item = {
            "id": worker_id,
            "resourceId": worker_id,
            "persona": "system",
            "domain": "operations",
            "kind": "worker_offline",
            "title": "教材 Worker 已離線",
            # Last-seen is part of the status so a recovered Worker can create a
            # new stable event key if a later outage occurs.
            "status": f"offline:{last_seen}",
            "statusLabel": "Worker 離線",
            "group": "",
            "area": "internal",
            "dueAt": "",
            "overdue": False,
            "detail": (
                f"{worker_id} 已超過 {threshold_minutes} 分鐘未回報心跳；"
                f"目前約離線 {offline_minutes} 分鐘。"
            ),
            "target": "worker",
        }
        output.append(_event(item))
    return output


def _operational_incident_events(
    user: Mapping[str, Any],
    current: dt.datetime,
) -> list[dict[str, Any]]:
    if not has_role(user, "system_admin"):
        return []
    output: list[dict[str, Any]] = []
    for incident in incidents.list_recent_incidents(now=current, resolved_hours=24):
        state = str(incident.get("status") or "")
        generation = int(incident.get("generation") or 1)
        incident_type = str(incident.get("incidentType") or "")
        is_recovery = state == "resolved"
        kind = (
            "operational_recovery"
            if is_recovery
            else "worker_offline"
            if incident_type == "worker_offline"
            else "operational_incident"
        )
        title = str(incident.get("title") or "系統維運事件")
        if is_recovery:
            title = f"{title}｜已恢復"
        item = {
            "id": str(incident.get("incidentKey") or ""),
            "resourceId": str(incident.get("incidentKey") or ""),
            "persona": "system",
            "domain": "operations",
            "kind": kind,
            "title": title,
            "status": f"{state}:{generation}",
            "statusLabel": "已恢復" if is_recovery else "需要處理",
            "group": "",
            "area": "internal",
            "dueAt": "",
            "overdue": False,
            "detail": (
                "系統已確認此維運事件恢復正常。"
                if is_recovery
                else str(incident.get("detail") or "")
            ),
            "target": "worker",
            "incidentType": incident_type,
            "severity": str(incident.get("severity") or ""),
            "errorCode": str(incident.get("errorCode") or ""),
            "action": (
                "目前不需要額外處理。"
                if is_recovery
                else str(incident.get("action") or "")
            ),
            "generation": generation,
            "responseState": str(incident.get("responseState") or ""),
            "assignedTo": str(incident.get("assignedTo") or ""),
            "maintenanceActive": bool(incident.get("maintenanceActive")),
            "maintenanceUntil": str(incident.get("maintenanceUntil") or ""),
        }
        event = _event(item)
        if bool(incident.get("maintenanceActive")) and not is_recovery:
            # Maintenance never hides the in-app incident. It only pauses a new
            # escalation email until the bounded maintenance window expires.
            event["channels"] = ["in_app"]
            event["emailPolicy"] = "none"
        output.append(event)
    return output


def build_events(
    user: Optional[Mapping[str, Any]],
    *,
    now: Optional[dt.datetime] = None,
    persona: str = "",
) -> dict[str, Any]:
    if not user:
        raise ApiError("LOGIN_REQUIRED", "請先登入後再查看通知。", status=401, extra={"loginRequired": True})
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)
    persona_mode = str(persona or "").strip().lower()
    command = service.build_summary(user, now=current, persona=persona_mode)
    events = [_event(item) for item in command.get("items") or []]
    incident_events = [] if persona_mode == "learner" else _operational_incident_events(user, current)
    events.extend(incident_events)
    if persona_mode != "learner" and not any(
        row.get("incidentType") == "worker_offline"
        and not str(row.get("kind") or "").endswith("recovery")
        for row in incident_events
    ):
        # Mixed-version fallback until the 10-minute incident sync has run.
        events.extend(_worker_offline_events(user, current))

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
        0 if row.get("kind") in {"review", "material_failure", "worker_offline", "operational_incident", "operational_recovery"} else 1,
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


def email_events(
    user: Mapping[str, Any],
    *,
    now: Optional[dt.datetime] = None,
    days: int = 7,
    milestones: tuple[int, ...] = (7, 3, 1),
) -> list[dict[str, Any]]:
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)
    maximum = max(1, int(days))
    configured = tuple(sorted({int(value) for value in milestones if int(value) > 0}))
    # A shortened EMAIL_REMINDER_DAYS value is a single configured horizon
    # (legacy/operational behavior), not a request to emit every smaller
    # canonical 7/3/1 milestone at once.  At the default/full horizon we keep
    # the nearest canonical milestone so 7d, 3d and 1d reminders have distinct
    # stable keys.
    if configured and maximum < max(configured):
        checkpoints = (maximum,)
    else:
        checkpoints = tuple(value for value in configured if value <= maximum)
    output = []
    for event in build_events(user, now=current)["items"]:
        if "email" not in event.get("channels", []):
            continue
        policy = event.get("emailPolicy")
        if policy == "once":
            output.append(event)
            continue
        due = _parse_datetime(event.get("dueAt"))
        if policy != "due" or not due or due <= current:
            continue
        remaining = due - current
        remaining_days = remaining.total_seconds() / 86400
        milestone = next((value for value in checkpoints if remaining_days <= value), None)
        if milestone is None:
            continue
        projected = dict(event)
        projected["reminderMilestoneDays"] = milestone
        projected["key"] = _stable_key("due_reminder", event.get("key"), milestone)
        projected["detail"] = (
            f"{str(event.get('detail') or '').strip()} · 距離截止約 {milestone} 天"
        ).strip(" ·")
        output.append(projected)
    return output


__all__ = ["build_events", "email_events"]
