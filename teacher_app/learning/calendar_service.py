"""Read-only learner calendar aggregation from canonical learning dates."""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping

from teacher_app.command_center import dashboard_service
from teacher_app.command_center import service as command_center_service
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.learning import access as learning_access


def _parse_datetime(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 10:
        text += "T00:00:00+00:00"
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _event(*, event_id: str, domain: str, kind: str, title: str, at: Any, area: str = "", group: str = "", course_id: str = "", target: str = "materials", overdue: bool = False) -> dict | None:
    parsed = _parse_datetime(at)
    if not parsed:
        return None
    return {"id": event_id, "domain": domain, "kind": kind, "title": title, "at": parsed.isoformat(), "date": parsed.date().isoformat(), "area": area, "group": group, "courseId": course_id, "target": target, "overdue": overdue}


def calendar_summary(user: Mapping[str, Any] | None, *, days: int = 90, now: dt.datetime | None = None) -> dict:
    if not user:
        raise ApiError("LOGIN_REQUIRED", "請先登入後再查看學習行事曆。", status=401, extra={"loginRequired": True})
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)
    days = max(7, min(180, int(days or 90)))
    lower = current - dt.timedelta(days=30)
    upper = current + dt.timedelta(days=days)
    events: list[dict] = []

    dashboard = dashboard_service.dashboard_summary(user, now=current)
    assignment_mode = bool(dashboard.get("assignmentMode"))
    assigned_course_ids = {
        str(item.get("courseId") or "").strip()
        for item in (dashboard.get("assignments") or [])
        if str(item.get("courseId") or "").strip()
    }
    for course in dashboard.get("pendingCourses") or []:
        if course.get("dueAt"):
            item = _event(event_id=f"course-due:{course.get('assignmentId') or course.get('id')}", domain="learning", kind="course_due", title=f"{course.get('title') or '課程'} 截止", at=course.get("dueAt"), area=str(course.get("area") or ""), group=str(course.get("group") or ""), course_id=str(course.get("id") or ""), target="materials", overdue=bool(course.get("overdue")))
            if item: events.append(item)

    for course in course_repository.list_courses(include_inactive=False):
        if not learning_access.can_access_learning_item(user, course):
            continue
        course_id = str(course.get("id") or ""); title = str(course.get("title") or "課程"); area = str(course.get("area") or ""); group = str(course.get("group") or "")
        if assignment_mode and course_id not in assigned_course_ids:
            continue
        for kind, value, suffix in (("course_start", course.get("startDate"), "開始"), ("course_end", course.get("endDate"), "建議完成")):
            item = _event(event_id=f"{kind}:{course_id}", domain="course", kind=kind, title=f"{title} {suffix}", at=value, area=area, group=group, course_id=course_id, target="materials")
            if item: events.append(item)

    command = command_center_service.build_summary(user, now=current)
    for task in command.get("items") or []:
        if task.get("domain") == "pgy" and task.get("dueAt"):
            item = _event(event_id=f"pgy-due:{task.get('id')}", domain="pgy", kind="pgy_due", title=f"{task.get('title') or 'PGY 訓練'} 截止", at=task.get("dueAt"), group=str(task.get("group") or ""), target="pgy-workflow", overdue=bool(task.get("overdue")))
            if item: events.append(item)

    unique = {item["id"]: item for item in events}
    visible = []
    for item in unique.values():
        at = _parse_datetime(item["at"])
        if not at or not (lower <= at <= upper):
            continue
        if at < current and not item.get("overdue"):
            continue
        visible.append(item)
    visible.sort(key=lambda item: (_parse_datetime(item["at"]), item["title"]))
    return {"generatedAt": current.isoformat(), "windowDays": days, "events": visible, "counts": {"total": len(visible), "overdue": sum(1 for item in visible if item.get("overdue")), "upcoming": sum(1 for item in visible if _parse_datetime(item["at"]) >= current)}}


__all__ = ["calendar_summary"]
