"""Canonical rules for general course learning assignments."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Mapping, Sequence

from teacher_app.common import scope
from teacher_app.common.auth import has_permission, has_role
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


def _require_actor(user: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not user:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入。",
            status=401,
            extra={"loginRequired": True},
        )
    return user


def _require_manager(user: Mapping[str, Any] | None) -> Mapping[str, Any]:
    actor = _require_actor(user)
    if not has_permission(actor, "learning.assign"):
        raise ApiError("FORBIDDEN", "權限不足。", status=403)
    return actor


def _global_manager(user: Mapping[str, Any]) -> bool:
    return has_role(user, "education_admin") or has_role(user, "system_admin")


def _assert_manager_scope(user: Mapping[str, Any], assignment: Mapping[str, Any]) -> None:
    if _global_manager(user):
        return
    if not has_role(user, "group_leader"):
        raise ApiError("FORBIDDEN", "權限不足。", status=403)
    _area, own_group = learning_access.preferred_learning_scope(user)
    if str(assignment.get("group") or assignment.get("group_key") or "") != own_group:
        raise ApiError("ASSIGNMENT_SCOPE_DENIED", "此課程不在你的組別範圍。", status=403)
    assignee_type = str(
        assignment.get("assigneeType") or assignment.get("assignee_type") or ""
    )
    if assignee_type and assignee_type != "group":
        raise ApiError(
            "ASSIGNMENT_SCOPE_DENIED",
            "組長只能建立或管理自己組別的整組課程指派。",
            status=403,
        )


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


def mine(user: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    actor = _require_actor(user)
    return list_for_user(actor)


def admin_list(
    actor: Mapping[str, Any] | None,
    *,
    area: str = "",
    group: str = "",
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    user = _require_manager(actor)
    rows = assignment_repository.list_assignments(include_inactive=include_inactive)
    try:
        wanted_area = (
            scope.validate_area(area, default=None) if str(area or "").strip() else ""
        )
        wanted_group = (
            scope.validate_group(group, default=None) if str(group or "").strip() else ""
        )
    except ValueError as exc:
        raise ApiError("INVALID_SCOPE", str(exc), status=400) from exc
    if not _global_manager(user):
        own_area, own_group = learning_access.preferred_learning_scope(user)
        if wanted_group and wanted_group != own_group:
            raise ApiError("ASSIGNMENT_SCOPE_DENIED", "此組別不在你的授權範圍。", status=403)
        wanted_area = wanted_area or own_area
        wanted_group = own_group

    values = []
    for item in rows:
        if wanted_area and str(item.get("area") or "") != wanted_area:
            continue
        if wanted_group and str(item.get("group") or "") != wanted_group:
            continue
        if not _global_manager(user) and str(item.get("assigneeType") or "") != "group":
            continue
        values.append(item)
    return values


def assigned_course_ids(user: Mapping[str, Any]) -> set[str]:
    return assignment_repository.course_ids(list_for_user(user))


def create_assignment(actor: Mapping[str, Any], data: Mapping[str, Any]) -> dict[str, Any]:
    user = _require_manager(actor)
    values = build_assignment(user, data)
    _assert_manager_scope(user, assignment_repository.assignment_to_dict(values))
    for existing in assignment_repository.list_assignments(include_inactive=True):
        if (
            str(existing.get("courseId") or "") == str(values.get("course_id") or "")
            and str(existing.get("assigneeType") or "") == str(values.get("assignee_type") or "")
            and str(existing.get("assigneeKey") or "") == str(values.get("assignee_key") or "")
        ):
            if existing.get("active", True):
                raise ApiError(
                    "ASSIGNMENT_EXISTS",
                    "此課程已經有相同對象的有效指派。",
                    status=409,
                )
            return assignment_repository.update_assignment(
                str(existing.get("id") or ""),
                required=bool(values.get("required", True)),
                due_at=str(values.get("due_at") or ""),
                active=True,
                updated_at=_now(),
            ) or existing
    return assignment_repository.insert_assignment(values)


def deactivate_assignment(assignment_id: str) -> dict[str, Any]:
    assignment = assignment_repository.get_assignment(assignment_id)
    if not assignment:
        raise ApiError("ASSIGNMENT_NOT_FOUND", "找不到學習指派。", status=404)
    return assignment_repository.set_active(
        assignment_id,
        False,
        updated_at=_now(),
    ) or assignment


def update_assignment(
    actor: Mapping[str, Any] | None,
    assignment_id: str,
    data: Mapping[str, Any],
) -> dict[str, Any]:
    user = _require_manager(actor)
    assignment = assignment_repository.get_assignment(assignment_id)
    if not assignment:
        raise ApiError("ASSIGNMENT_NOT_FOUND", "找不到學習指派。", status=404)
    _assert_manager_scope(user, assignment)
    if not isinstance(data, Mapping):
        raise ApiError("INVALID_ASSIGNMENT", "指派資料格式不正確。", status=400)
    allowed = {"required", "dueAt", "active"}
    if any(key not in allowed for key in data):
        raise ApiError(
            "ASSIGNMENT_UPDATE_INVALID",
            "只能調整必修狀態、截止時間或啟用狀態。",
            status=400,
        )
    required = bool(data.get("required", assignment.get("required", True)))
    due_at = (
        _parse_due(data.get("dueAt"))
        if "dueAt" in data
        else str(assignment.get("dueAt") or "")
    )
    active = bool(data.get("active", assignment.get("active", True)))
    return assignment_repository.update_assignment(
        assignment_id,
        required=required,
        due_at=due_at,
        active=active,
        updated_at=_now(),
    ) or assignment


__all__ = [
    "ASSIGNEE_TYPES",
    "TYPE_PRIORITY",
    "assigned_course_ids",
    "build_assignment",
    "create_assignment",
    "deactivate_assignment",
    "admin_list",
    "list_for_user",
    "mine",
    "resolve_assignments",
    "update_assignment",
]
