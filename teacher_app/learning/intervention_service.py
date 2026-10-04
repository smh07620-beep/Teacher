"""F3 training intervention workflow.

Cases track teacher follow-up but never overwrite learning, exam, qualification,
or certificate evidence. Resolution is accepted only after canonical evidence
no longer reports the source abnormality.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any, Mapping

from teacher_app.auth import accounts
from teacher_app.common import audit
from teacher_app.common.auth import has_permission
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.exams import remediation
from teacher_app.learning import compliance_service, intervention_repository
from teacher_app.materials import repository as material_repository


MANAGED_SOURCE_STATUSES = {"overdue", "retraining", "remediation"}
CASE_STATUSES = {"open", "in_progress", "ready_for_retest", "resolved", "cancelled"}
ACTIVE_CASE_STATUSES = intervention_repository.ACTIVE_STATUSES


def _fail(code: str, message: str, status: int, **extra) -> ApiError:
    return ApiError(code, message, status=status, extra=extra or None)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _manager(actor: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not actor:
        raise _fail("LOGIN_REQUIRED", "請先登入。", 401)
    if not (
        has_permission(actor, "training.compliance.read")
        and has_permission(actor, "learning.assign")
    ):
        raise _fail("FORBIDDEN", "此帳號沒有訓練介入管理權限。", 403)
    return actor


def _username(actor: Mapping[str, Any] | None) -> str:
    return str((actor or {}).get("username") or "").strip().lower()


def _account(username: str) -> dict | None:
    wanted = str(username or "").strip().lower()
    for account in accounts.list_accounts():
        if str(account.get("username") or "").strip().lower() == wanted:
            return dict(account)
    return None


def _current_row(
    actor: Mapping[str, Any],
    username: str,
    course_id: str,
) -> dict:
    matrix = compliance_service.build_matrix(
        actor,
        course_id=str(course_id or ""),
        include_inactive_users=True,
    )
    wanted = str(username or "").strip().lower()
    row = next(
        (
            item
            for item in matrix.get("rows", [])
            if str(item.get("username") or "").strip().lower() == wanted
            and str(item.get("courseId") or "") == str(course_id or "")
        ),
        None,
    )
    if not row:
        raise _fail(
            "INTERVENTION_TARGET_NOT_VISIBLE",
            "找不到此授權範圍內的學員課程紀錄。",
            404,
        )
    return dict(row)


def _material_projection(item: Mapping[str, Any]) -> dict:
    return {
        "id": str(item.get("id") or ""),
        "title": str(item.get("title") or item.get("filename") or "教材"),
        "currentVersion": int(item.get("currentVersion") or item.get("version") or 1),
        "requiredCompletionVersion": int(item.get("requiredCompletionVersion") or 1),
    }


def _plan_for(row: Mapping[str, Any]) -> dict:
    status = str(row.get("status") or "")
    course_id = str(row.get("courseId") or "")
    materials = [
        item
        for item in material_repository.list_uploaded_materials(include_inactive=False)
        if str(item.get("courseId") or "") == course_id
        and item.get("active", True)
    ]
    if status == "remediation":
        exam = dict((row.get("evidence") or {}).get("exam") or {})
        plan = remediation.build_plan(
            score=exam.get("score", 0),
            passing_score=exam.get("passingScore", 80),
            essay_count=0,
            quiz_category_id=exam.get("quizCategoryId", ""),
            course_id=course_id,
            area=row.get("area"),
            group=row.get("group"),
            materials=materials,
        )
        return {
            "type": "remediation",
            "courseId": course_id,
            "courseTitle": str(row.get("courseTitle") or ""),
            "reviewMaterials": list(plan.get("reviewMaterials") or []),
            "score": plan.get("score"),
            "passingScore": plan.get("passingScore"),
            "scoreGap": plan.get("scoreGap"),
            "quizCategoryId": plan.get("quizCategoryId"),
            "recommendedNextAction": "review_then_retest",
        }
    if status == "retraining":
        ids = {
            str(item)
            for item in row.get("retrainingMaterialIds", [])
            if str(item)
        }
        selected = [item for item in materials if not ids or str(item.get("id") or "") in ids]
        return {
            "type": "retraining",
            "courseId": course_id,
            "courseTitle": str(row.get("courseTitle") or ""),
            "reviewMaterials": [_material_projection(item) for item in selected[:20]],
            "recommendedNextAction": "complete_required_versions",
        }
    return {
        "type": "overdue",
        "courseId": course_id,
        "courseTitle": str(row.get("courseTitle") or ""),
        "dueAt": str(row.get("dueAt") or ""),
        "materialsCompleted": int(row.get("materialsCompleted") or 0),
        "materialsTotal": int(row.get("materialsTotal") or 0),
        "examStatus": str(row.get("examStatus") or ""),
        "recommendedNextAction": "complete_overdue_requirement",
    }


def _default_message(row: Mapping[str, Any]) -> str:
    status = str(row.get("status") or "")
    title = str(row.get("courseTitle") or "此課程")
    if status == "remediation":
        return f"{title} 的考核尚未達到通過標準，請先完成補強教材後再進行測驗。"
    if status == "retraining":
        return f"{title} 有教材重大更新，請完成目前要求版本的重新閱讀。"
    return f"{title} 已超過原訂完成期限，請優先完成剩餘學習項目。"


def _public(case: Mapping[str, Any]) -> dict:
    item = dict(case)
    item.pop("internalNote", None)
    item.pop("createdBy", None)
    item.pop("updatedBy", None)
    course = course_repository.get_course(str(item.get("courseId") or "")) or {}
    item["courseTitle"] = str(course.get("title") or item.get("plan", {}).get("courseTitle") or "")
    return item


def create_or_refresh(
    actor: Mapping[str, Any] | None,
    payload: Mapping[str, Any] | None,
) -> dict:
    manager = _manager(actor)
    body = dict(payload or {})
    username = str(body.get("username") or "").strip().lower()
    course_id = str(body.get("courseId") or "").strip()
    if not username or not course_id:
        raise _fail("INTERVENTION_TARGET_REQUIRED", "請指定學員與課程。", 400)

    row = _current_row(manager, username, course_id)
    source_status = str(row.get("status") or "")
    if source_status not in MANAGED_SOURCE_STATUSES:
        raise _fail(
            "INTERVENTION_NOT_REQUIRED",
            "目前沒有逾期、重訓或補強狀態，不需建立介入案件。",
            409,
            currentStatus=source_status,
        )
    learner_message = str(body.get("learnerMessage") or "").strip()[:1200]
    internal_note = str(body.get("internalNote") or "").strip()[:3000]
    plan = _plan_for(row)
    now = _now()
    actor_username = _username(manager)
    existing = intervention_repository.find_active(username, course_id)

    if existing:
        updated = intervention_repository.update_intervention(
            existing["id"],
            source_status=source_status,
            kind=source_status,
            learner_message=learner_message or existing.get("learnerMessage") or _default_message(row),
            internal_note=internal_note if "internalNote" in body else existing.get("internalNote", ""),
            plan_json=json.dumps(plan, ensure_ascii=False, separators=(",", ":")),
            updated_by=actor_username,
            updated_at=now,
        ) or existing
        audit.record_event(
            actor=manager,
            action="training.intervention.refresh",
            target_type="training_intervention",
            target_id=updated.get("id", ""),
            group=str(row.get("group") or ""),
            before=existing,
            after=updated,
            detail={"sourceStatus": source_status},
        )
        return {"created": False, "intervention": updated}

    intervention_id = "INT-" + uuid.uuid4().hex[:20].upper()
    created = intervention_repository.insert_intervention(
        {
            "id": intervention_id,
            "username": username,
            "emp_id": str(row.get("empId") or ""),
            "course_id": course_id,
            "source_status": source_status,
            "kind": source_status,
            "status": "open",
            "learner_message": learner_message or _default_message(row),
            "internal_note": internal_note,
            "plan_json": json.dumps(plan, ensure_ascii=False, separators=(",", ":")),
            "created_by": actor_username,
            "created_at": now,
            "updated_by": actor_username,
            "updated_at": now,
            "resolved_at": "",
            "resolution_json": "{}",
        }
    )
    audit.record_event(
        actor=manager,
        action="training.intervention.create",
        target_type="training_intervention",
        target_id=intervention_id,
        group=str(row.get("group") or ""),
        after=created or {},
        detail={"sourceStatus": source_status},
    )
    return {"created": True, "intervention": created}


def update_case(
    actor: Mapping[str, Any] | None,
    intervention_id: str,
    payload: Mapping[str, Any] | None,
) -> dict:
    manager = _manager(actor)
    current = intervention_repository.get_intervention(intervention_id)
    if not current:
        raise _fail("INTERVENTION_NOT_FOUND", "找不到此介入案件。", 404)
    row = _current_row(manager, current["username"], current["courseId"])
    if current.get("status") in intervention_repository.TERMINAL_STATUSES:
        raise _fail("INTERVENTION_CLOSED", "此介入案件已結案，不能再修改。", 409)

    body = dict(payload or {})
    target_status = str(body.get("status") or current.get("status") or "open").strip()
    if target_status not in CASE_STATUSES:
        raise _fail("INTERVENTION_STATUS_INVALID", "介入案件狀態不正確。", 400)
    if target_status == "ready_for_retest" and current.get("kind") != "remediation":
        raise _fail("INTERVENTION_RETEST_NOT_APPLICABLE", "只有補強案件可標記為準備再測。", 409)

    source_status = str(row.get("status") or "")
    resolved_at = None
    resolution = None
    if target_status == "resolved":
        if source_status in MANAGED_SOURCE_STATUSES:
            raise _fail(
                "INTERVENTION_STILL_REQUIRED",
                "目前真實學習／考核證據仍顯示需介入，不能直接結案。",
                409,
                currentStatus=source_status,
            )
        resolved_at = _now()
        resolution = {
            "evidenceStatus": source_status,
            "completed": bool(row.get("completed")),
            "examPassed": bool(row.get("examPassed")),
            "materialsComplete": bool(row.get("materialsComplete")),
            "verifiedAt": resolved_at,
        }
    elif target_status == "cancelled":
        resolved_at = _now()
        resolution = {
            "cancelled": True,
            "evidenceStatus": source_status,
            "verifiedAt": resolved_at,
        }

    learner_message = None
    if "learnerMessage" in body:
        learner_message = str(body.get("learnerMessage") or "").strip()[:1200]
    internal_note = None
    if "internalNote" in body:
        internal_note = str(body.get("internalNote") or "").strip()[:3000]
    plan = _plan_for(row) if source_status in MANAGED_SOURCE_STATUSES else current.get("plan", {})
    updated_at = _now()
    updated = intervention_repository.update_intervention(
        intervention_id,
        source_status=source_status,
        kind=source_status if source_status in MANAGED_SOURCE_STATUSES else current.get("kind"),
        status=target_status,
        learner_message=learner_message,
        internal_note=internal_note,
        plan_json=json.dumps(plan, ensure_ascii=False, separators=(",", ":")),
        updated_by=_username(manager),
        updated_at=updated_at,
        resolved_at=resolved_at,
        resolution_json=(
            json.dumps(resolution, ensure_ascii=False, separators=(",", ":"))
            if resolution is not None
            else None
        ),
    )
    audit.record_event(
        actor=manager,
        action=f"training.intervention.{target_status}",
        target_type="training_intervention",
        target_id=intervention_id,
        group=str(row.get("group") or ""),
        before=current,
        after=updated or {},
        detail={"evidenceStatus": source_status},
    )
    return {"ok": True, "intervention": updated}


def manager_list(
    actor: Mapping[str, Any] | None,
    *,
    area: str = "",
    group: str = "",
    course_id: str = "",
    status: str = "",
) -> dict:
    manager = _manager(actor)
    matrix = compliance_service.build_matrix(
        manager,
        area=area,
        group=group,
        course_id=course_id,
        include_inactive_users=True,
    )
    visible_pairs = {
        (str(item.get("username") or "").lower(), str(item.get("courseId") or ""))
        for item in matrix.get("rows", [])
    }
    rows = intervention_repository.list_interventions(
        course_id=course_id,
        status=status,
        include_terminal=True,
    )
    items = [
        item
        for item in rows
        if (item.get("username"), item.get("courseId")) in visible_pairs
    ]
    return {
        "scope": matrix.get("scope", {}),
        "summary": {
            "total": len(items),
            "open": sum(1 for item in items if item.get("status") == "open"),
            "inProgress": sum(1 for item in items if item.get("status") == "in_progress"),
            "readyForRetest": sum(1 for item in items if item.get("status") == "ready_for_retest"),
            "resolved": sum(1 for item in items if item.get("status") == "resolved"),
            "cancelled": sum(1 for item in items if item.get("status") == "cancelled"),
        },
        "items": items,
    }


def mine(actor: Mapping[str, Any] | None, *, include_closed: bool = False) -> dict:
    username = _username(actor)
    if not username:
        raise _fail("LOGIN_REQUIRED", "請先登入。", 401)
    rows = intervention_repository.list_interventions(
        username=username,
        include_terminal=include_closed,
    )
    return {
        "items": [_public(item) for item in rows],
        "activeCount": sum(1 for item in rows if item.get("status") in ACTIVE_CASE_STATUSES),
    }


__all__ = [
    "ACTIVE_CASE_STATUSES",
    "CASE_STATUSES",
    "MANAGED_SOURCE_STATUSES",
    "create_or_refresh",
    "manager_list",
    "mine",
    "update_case",
]
