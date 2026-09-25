"""Canonical rules for general course learning assignments."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Mapping, Sequence

from teacher_app.common import scope
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.learning import access as learning_access
from teacher_app.learning import assignment_repository


ASSIGNEE_TYPES = {"user", "group", "all"}
TYPE_PRIORITY = {"all": 0, "group": 1, "user": 2}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _username(user: Mapping[str, Any] | None) -> str:
    return str((user or {}).get("username") or "").strip().lower()


def _parse_due(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ApiError("INVALID_ASSIGNMENT_DUE_AT", "截止時間格式不正確。", status=400) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).isoformat()


def _assignee_key(assignee_type: str, value: Any, *, course_group: str) -> str:
    raw = str(value or "").strip()
    if assignee_type == "user":
        if not raw:
            raise ApiError("ASSIGNEE_REQUIRED", "個人指派必須指定使用者。", status=400)
        return raw.lower()[:120]
    if assignee_type == "group":
        requested = scope.normalize_group(raw or course_group)
        if requested != course_group:
            raise ApiError(
                "ASSIGNMENT_SCOPE_MISMATCH",
                "組別指派必須與課程所屬組別一致。",
                status=400,
            )
        return requested
    return "*"


def build_assignment(
    actor: Mapping[str, Any],
    data: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise ApiError("INVALID_ASSIGNMENT", "指派資料格式不正確。", status=400)
    course_id = str(data.get("courseId") or "").strip()
    course = course_repository.get_course(course_id)
    if not course:
        raise ApiError("COURSE_NOT_FOUND", "找不到課程。", status=404)

    assignee_type = str(data.get("assigneeType") or "").strip().lower()
    if assignee_type not in ASSIGNEE_TYPES:
        raise ApiError(
            "INVALID_ASSIGNEE_TYPE",
            "指派對象必須是個人、組別或全體。",
            status=400,
        )

    course_area = scope.normalize_area(course.get("area"))
    course_group = scope.normalize_group(course.get("group"))
    key = _assignee_key(
        assignee_type,
        data.get("assigneeKey"),
        course_group=course_group,
    )
    now = _now()
    return {
        "id": f"la-{uuid.uuid4().hex[:16]}",
        "course_id": course_id,
        "training_area": course_area,
        "group_key": course_group,
        "assignee_type": assignee_type,
        "assignee_key": key,
        "required": bool(data.get("required", True)),
        "due_at": _parse_due(data.get("dueAt")),
        "assigned_at": now,
        "assigned_by": _username(actor),
        "active": True,
        "created_at": now,
        "updated_at": now,
    }


def resolve_assignments(
    assignments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse overlapping all/group/user rows into one course-level obligation."""
    merged: dict[str, dict[str, Any]] = {}
    for raw in assignments:
        item = dict(raw)
        course_id = str(item.get("courseId") or "").strip()
        if not course_id:
            continue
        current = merged.get(course_id)
        if current is None:
            current = dict(item)
            current["sourceAssignmentIds"] = [str(item.get("id") or "")]
            merged[course_id] = current
            continue

        current["sourceAssignmentIds"].append(str(item.get("id") or ""))
        current["required"] = bool(current.get("required")) or bool(item.get("required"))
        due_values = [
            str(value or "").strip()
            for value in (current.get("dueAt"), item.get("dueAt"))
            if str(value or "").strip()
        ]
        current["dueAt"] = min(due_values) if due_values else ""
        if TYPE_PRIORITY.get(str(item.get("assigneeType") or ""), -1) > TYPE_PRIORITY.get(
            str(current.get("assigneeType") or ""), -1
        ):
            for key in ("id", "assigneeType", "assigneeKey", "assignedAt", "assignedBy"):
                current[key] = item.get(key)

    values = list(merged.values())
    values.sort(
        key=lambda item: (
            0 if item.get("required") else 1,
            str(item.get("dueAt") or "9999"),
            str(item.get("courseId") or ""),
        )
    )
    return values


def list_for_user(user: Mapping[str, Any]) -> list[dict[str, Any]]:
    username = _username(user)
    if not username:
        return []
    area, group = learning_access.preferred_learning_scope(user)
    rows = assignment_repository.list_for_user(
        username=username,
        area=area,
        group=group,
    )
    return resolve_assignments(rows)


def assigned_course_ids(user: Mapping[str, Any]) -> set[str]:
    return assignment_repository.course_ids(list_for_user(user))


def create_assignment(actor: Mapping[str, Any], data: Mapping[str, Any]) -> dict[str, Any]:
    return assignment_repository.insert_assignment(build_assignment(actor, data))


def deactivate_assignment(assignment_id: str) -> dict[str, Any]:
    assignment = assignment_repository.get_assignment(assignment_id)
    if not assignment:
        raise ApiError("ASSIGNMENT_NOT_FOUND", "找不到學習指派。", status=404)
    return assignment_repository.set_active(
        assignment_id,
        False,
        updated_at=_now(),
    ) or assignment


__all__ = [
    "ASSIGNEE_TYPES",
    "TYPE_PRIORITY",
    "assigned_course_ids",
    "build_assignment",
    "create_assignment",
    "deactivate_assignment",
    "list_for_user",
    "resolve_assignments",
]
