"""Read-only training compliance projection for manager workspaces.

This module owns no completion rules. It expands canonical learning assignments
per account and projects existing progress, retraining, remediation and
certificate evidence into manager-facing rows.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping

from teacher_app.auth import accounts
from teacher_app.common import scope
from teacher_app.common.auth import has_permission, has_role
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.learning import access as learning_access
from teacher_app.learning import assignment_service
from teacher_app.learning import certificate_service
from teacher_app.learning import progress_service


STATUSES = {
    "complete",
    "overdue",
    "retraining",
    "remediation",
    "pending_review",
    "awaiting_exam",
    "in_progress",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _global_manager(user: Mapping[str, Any]) -> bool:
    return has_role(user, "education_admin") or has_role(user, "system_admin")


def _require_actor(user: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not user:
        raise ApiError("LOGIN_REQUIRED", "請先登入。", status=401)
    if not has_permission(user, "training.compliance.read"):
        raise ApiError("FORBIDDEN", "權限不足。", status=403)
    return user


def _manager_scope(actor: Mapping[str, Any], *, area: str = "", group: str = "") -> tuple[str, str]:
    try:
        wanted_area = scope.validate_area(area, default=None) if _text(area) else ""
        wanted_group = scope.validate_group(group, default=None) if _text(group) else ""
    except ValueError as exc:
        raise ApiError("INVALID_SCOPE", str(exc), status=400) from exc
    if _global_manager(actor):
        return wanted_area, wanted_group
    if not has_role(actor, "group_leader"):
        raise ApiError("FORBIDDEN", "權限不足。", status=403)
    own_area = scope.normalize_area(actor.get("preferredArea") or actor.get("preferred_area"))
    own_group = scope.normalize_group(actor.get("preferredGroup") or actor.get("preferred_group"))
    if wanted_area and wanted_area != own_area:
        raise ApiError("COMPLIANCE_SCOPE_DENIED", "此訓練區不在你的授權範圍。", status=403)
    if wanted_group and wanted_group != own_group:
        raise ApiError("COMPLIANCE_SCOPE_DENIED", "此組別不在你的授權範圍。", status=403)
    return own_area, own_group


def _parse_due(value: Any) -> dt.datetime | None:
    text_value = _text(value)
    if not text_value:
        return None
    candidate = text_value[:-1] + "+00:00" if text_value.endswith("Z") else text_value
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _exam_state(completion: Mapping[str, Any], records: list[Mapping[str, Any]]) -> str:
    if not completion.get("examRequired"):
        return "not_required"
    if completion.get("examPassed"):
        return "passed"
    required_ids = {_text(item) for item in completion.get("requiredExamIds", []) if _text(item)}
    relevant = [record for record in records if _text(record.get("courseId")) == _text(completion.get("id")) and (not required_ids or _text(record.get("quizCategoryId")) in required_ids)]
    for record in relevant:
        if _text(record.get("reviewStatus")) == "pending":
            return "pending_review"
        try:
            passed = float(record.get("score", 0) or 0) >= float(record.get("passingScore", 80) or 80)
        except (TypeError, ValueError):
            passed = False
        if _text(record.get("reviewStatus") or "completed") == "completed" and not passed:
            return "remediation"
    return "not_started"


def _row_status(*, completion: Mapping[str, Any], due_at: str, required: bool, retraining: bool, exam_state: str, now: dt.datetime) -> str:
    if completion.get("completed"):
        return "complete"
    due = _parse_due(due_at)
    if required and due is not None and due < now:
        return "overdue"
    if retraining:
        return "retraining"
    if exam_state == "pending_review":
        return "pending_review"
    if exam_state == "remediation":
        return "remediation"
    if completion.get("materialsComplete") and completion.get("examRequired"):
        return "awaiting_exam"
    return "in_progress"


def _certificate_projection(certificates: list[Mapping[str, Any]], course_id: str) -> dict[str, Any]:
    matches = [item for item in certificates if _text(item.get("courseId")) == course_id]
    current = next((item for item in matches if item.get("currentValid")), None)
    latest = current or (matches[0] if matches else None)
    return {
        "certificateCount": len(matches),
        "certificateId": _text((latest or {}).get("id")),
        "certificateStatus": "current" if current else "historical" if matches else "none",
        "certificateIssuedAt": _text((latest or {}).get("issuedAt")),
    }


def build_matrix(actor: Mapping[str, Any] | None, *, area: str = "", group: str = "", course_id: str = "", status: str = "", include_inactive_users: bool = False, now: dt.datetime | None = None) -> dict[str, Any]:
    manager = _require_actor(actor)
    wanted_area, wanted_group = _manager_scope(manager, area=area, group=group)
    wanted_course = _text(course_id)
    wanted_status = _text(status).lower()
    if wanted_status and wanted_status not in STATUSES:
        raise ApiError("INVALID_COMPLIANCE_STATUS", "合規狀態篩選值不正確。", status=400)
    current_time = now or dt.datetime.now(dt.timezone.utc)
    rows: list[dict[str, Any]] = []
    progress_cache: dict[tuple[str, str, str], dict[str, Any]] = {}
    certificate_cache: dict[str, list[dict[str, Any]]] = {}

    for user in accounts.list_accounts():
        if not include_inactive_users and not bool(user.get("active", True)):
            continue
        user_area = scope.normalize_area(user.get("preferredArea"))
        user_group = scope.normalize_group(user.get("preferredGroup"))
        if wanted_area and user_area != wanted_area:
            continue
        if wanted_group and user_group != wanted_group:
            continue
        assignments = assignment_service.list_for_user(user)
        if not assignments:
            continue
        username = _text(user.get("username")).lower()
        cache_key = (username, user_area, user_group)
        if cache_key not in progress_cache:
            progress_cache[cache_key] = progress_service.my_progress(user, area=user_area, group=user_group)
        progress = progress_cache[cache_key]
        if username not in certificate_cache:
            certificate_cache[username] = certificate_service.list_certificates(user)
        certificates = certificate_cache[username]
        courses = {_text(item.get("id")): item for item in progress.get("courses", []) if _text(item.get("id"))}
        stale_material_ids = {_text(item) for item in progress.get("materialsRetraining", []) if _text(item)}

        for assignment in assignments:
            assignment_course_id = _text(assignment.get("courseId"))
            if not assignment_course_id or (wanted_course and assignment_course_id != wanted_course):
                continue
            completion = courses.get(assignment_course_id)
            if completion is None:
                course = course_repository.get_course(assignment_course_id) or {}
                if not course:
                    continue
                if not learning_access.can_access_learning_item(user, course):
                    continue
                completion = {**course, "completed": False, "materialsTotal": 0, "materialsCompleted": 0, "materialsComplete": False, "examRequired": False, "examPassed": False, "requiredMaterialIds": [], "requiredExamIds": []}
            required_material_ids = {_text(item) for item in completion.get("requiredMaterialIds", []) if _text(item)}
            retraining = bool(required_material_ids & stale_material_ids)
            exam_state = _exam_state(completion, list(progress.get("records", [])))
            row_status = _row_status(completion=completion, due_at=_text(assignment.get("dueAt")), required=bool(assignment.get("required", True)), retraining=retraining, exam_state=exam_state, now=current_time)
            if wanted_status and row_status != wanted_status:
                continue
            row = {
                "username": username,
                "name": _text(user.get("name")) or username,
                "empId": _text(user.get("empId")),
                "role": _text(user.get("role")),
                "area": user_area,
                "group": user_group,
                "courseId": assignment_course_id,
                "courseTitle": _text(completion.get("title")) or assignment_course_id,
                "required": bool(assignment.get("required", True)),
                "dueAt": _text(assignment.get("dueAt")),
                "assignedAt": _text(assignment.get("assignedAt")),
                "assignmentSourceIds": list(assignment.get("sourceAssignmentIds") or [assignment.get("id")]),
                "materialsCompleted": int(completion.get("materialsCompleted", 0) or 0),
                "materialsTotal": int(completion.get("materialsTotal", 0) or 0),
                "materialsComplete": bool(completion.get("materialsComplete")),
                "retrainingRequired": retraining,
                "examRequired": bool(completion.get("examRequired")),
                "examPassed": bool(completion.get("examPassed")),
                "examStatus": exam_state,
                "completed": bool(completion.get("completed")),
                "status": row_status,
            }
            row.update(_certificate_projection(certificates, assignment_course_id))
            rows.append(row)

    rows.sort(key=lambda item: (0 if item["status"] == "overdue" else 1, 0 if item["status"] == "retraining" else 1, _text(item.get("dueAt")) or "9999", _text(item.get("group")), _text(item.get("name")), _text(item.get("courseTitle"))))
    counts = {key: 0 for key in STATUSES}
    for item in rows:
        counts[item["status"]] += 1
    return {
        "scope": {"area": wanted_area, "group": wanted_group},
        "filters": {"courseId": wanted_course, "status": wanted_status},
        "summary": {"total": len(rows), "complete": counts["complete"], "overdue": counts["overdue"], "retraining": counts["retraining"], "remediation": counts["remediation"], "pendingReview": counts["pending_review"], "awaitingExam": counts["awaiting_exam"], "inProgress": counts["in_progress"]},
        "rows": rows,
    }


__all__ = ["STATUSES", "build_matrix"]
