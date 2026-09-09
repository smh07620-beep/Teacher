"""PGY business rules and transactional workflow orchestration."""

from __future__ import annotations

import uuid
from typing import Any, Mapping, Optional, Sequence

from teacher_app.common.auth import normalize_role
from teacher_app.common.db import get_connection, placeholder, transaction
from teacher_app.common.errors import ApiError
from teacher_app.pgy import repository as repo
from teacher_app.pgy.workflow import (
    ASSIGNMENT_STATUSES,
    ASSIGNMENT_VIEW_ROLES,
    AUDIT_VIEW_ROLES,
    CANDIDATE_ROLES,
    actions_for_role,
    can_cancel,
    can_reopen,
    expected_status_for,
    normalize_group,
    target_status_for,
    transition_allowed,
    utcnow,
)


def _username(value: Any) -> str:
    return str(value or "").strip().lower()[:100]


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _role(user: Optional[Mapping[str, Any]]) -> str:
    return normalize_role((user or {}).get("role", "student"))


def _user_group(user: Mapping[str, Any]) -> str:
    return normalize_group(user.get("preferredGroup") or user.get("preferred_group"))


def require_login(user: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    if not user:
        raise ApiError("LOGIN_REQUIRED", "請先登入後再執行此操作。", status=401, extra={"loginRequired": True})
    return user


def require_pgy_roles(user: Optional[Mapping[str, Any]], allowed: Sequence[str]) -> Mapping[str, Any]:
    actor = require_login(user)
    if _role(actor) not in {normalize_role(r) for r in allowed}:
        raise ApiError("FORBIDDEN", "權限不足。", status=403)
    return actor


def _can_view(user: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    role = _role(user)
    username = _username(user.get("username"))
    if role == "education_admin":
        return True
    if role == "student":
        return row.get("learner_username") == username
    if role == "clinical_teacher":
        return row.get("teacher_username") == username
    if role == "group_leader":
        return row.get("group_key") == _user_group(user)
    return False


def workflow_meta(user: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    actor = require_login(user)
    role = _role(actor)
    return {
        "statuses": sorted(ASSIGNMENT_STATUSES),
        "actions": actions_for_role(role),
        "role": role,
        "signatureOrder": ["student", "clinical_teacher", "group_leader", "education_admin"],
    }


def list_assignment_candidates(user: Optional[Mapping[str, Any]], group: str = "") -> dict[str, Any]:
    actor = require_pgy_roles(user, CANDIDATE_ROLES)
    requested_group = normalize_group(group or _user_group(actor))
    if _role(actor) == "group_leader" and requested_group != _user_group(actor):
        raise ApiError("FORBIDDEN", "組長只能查看自己組別的指派候選人。", status=403)
    conn, kind = get_connection()
    try:
        students, teachers = repo.find_assignment_candidates(conn, kind, requested_group)
        return {"group": requested_group, "students": students, "teachers": teachers}
    finally:
        conn.close()


def list_assignments(user: Optional[Mapping[str, Any]], *, status: str = "", group: str = "") -> list[dict[str, Any]]:
    actor = require_pgy_roles(user, ASSIGNMENT_VIEW_ROLES)
    conn, kind = get_connection()
    try:
        ph = placeholder(kind)
        role = _role(actor)
        where = ["a.training_area='pgy'"]
        params: list[Any] = []
        if role == "student":
            where.append(f"a.learner_username={ph}")
            params.append(_username(actor.get("username")))
        elif role == "clinical_teacher":
            where.append(f"a.teacher_username={ph}")
            params.append(_username(actor.get("username")))
        elif role == "group_leader":
            where.append(f"a.group_key={ph}")
            params.append(_user_group(actor))
        status = _text(status, 40)
        if status:
            if status not in ASSIGNMENT_STATUSES:
                raise ApiError("INVALID_STATUS", "狀態格式不正確。", status=400)
            where.append(f"a.status={ph}")
            params.append(status)
        group = _text(group, 40)
        if group and role == "education_admin":
            where.append(f"a.group_key={ph}")
            params.append(normalize_group(group))
        rows = repo.list_assignments(conn, kind, " AND ".join(where), params)
        return [repo.assignment_dict(row) for row in rows]
    finally:
        conn.close()


def get_assignment(user: Optional[Mapping[str, Any]], assignment_id: str) -> dict[str, Any]:
    actor = require_pgy_roles(user, ASSIGNMENT_VIEW_ROLES)
    conn, kind = get_connection()
    try:
        row = repo.get_assignment(conn, kind, assignment_id)
        if not row:
            raise ApiError("ASSIGNMENT_NOT_FOUND", "找不到指派。", status=404)
        if not _can_view(actor, row):
            raise ApiError("FORBIDDEN", "無權查看此指派。", status=403)
        return repo.assignment_dict(row)
    finally:
        conn.close()


def create_assignment(user: Optional[Mapping[str, Any]], data: Mapping[str, Any]) -> dict[str, Any]:
    actor = require_pgy_roles(user, {"education_admin"})
    learner_username = _username(data.get("learnerUsername"))
    teacher_username = _username(data.get("teacherUsername"))
    if not learner_username or not teacher_username:
        raise ApiError("INVALID_ASSIGNMENT", "學員與臨床教師皆為必填。", status=400)
    area = _text(data.get("area") or "pgy", 20)
    if area != "pgy":
        raise ApiError("INVALID_AREA", "PGY 指派只能建立在 PGY 訓練區。", status=400)
    with transaction() as (conn, kind):
        learner = repo.find_user(conn, kind, learner_username)
        teacher = repo.find_user(conn, kind, teacher_username)
        if not learner or not bool(learner.get("active", True)) or normalize_role(learner.get("role")) != "student":
            raise ApiError("INVALID_LEARNER", "指定的學員不存在、已停用或角色不是學員。", status=400)
        if not teacher or not bool(teacher.get("active", True)) or normalize_role(teacher.get("role")) != "clinical_teacher":
            raise ApiError("INVALID_TEACHER", "指定的教師不存在、已停用或角色不是臨床教師。", status=400)
        group = normalize_group(data.get("group") or learner.get("preferred_group"))
        course_id = _text(data.get("courseId"), 120)
        course = repo.find_course(conn, kind, course_id) if course_id else None
        if course_id and not course:
            raise ApiError("COURSE_NOT_FOUND", "找不到指定課程。", status=400)
        if course:
            course_area = str(course.get("training_area") or "")
            course_group = normalize_group(course.get("group_key"))
            if course_area != "pgy" or course_group != group:
                raise ApiError("COURSE_MISMATCH", "課程的訓練區或組別與指派不一致。", status=400)
        if course_id and repo.find_active_assignment_for_course(conn, kind, learner_username, course_id):
            raise ApiError("DUPLICATE_ASSIGNMENT", "此學員在同一課程已有進行中的指派。", status=409)
        assignment_id = uuid.uuid4().hex
        now = utcnow()
        title = _text(data.get("title") or (course or {}).get("title") or "PGY訓練指派", 180)
        instructions = _text(data.get("instructions"), 10000)
        due_at = _text(data.get("dueAt"), 80)
        repo.create_assignment(
            conn,
            kind,
            assignment_id=assignment_id,
            learner_username=learner_username,
            teacher_username=teacher_username,
            group_key=group,
            course_id=course_id,
            title=title,
            instructions=instructions,
            due_at=due_at,
            created_by=_username(actor.get("username")),
            created_at=now,
        )
        repo.write_audit(
            conn,
            kind,
            assignment_id=assignment_id,
            action="create",
            from_status="",
            to_status="assigned",
            actor_username=_username(actor.get("username")),
            actor_role=_role(actor),
            detail={
                "learnerUsername": learner_username,
                "teacherUsername": teacher_username,
                "courseId": course_id,
                "group": group,
            },
        )
        row = repo.get_assignment(conn, kind, assignment_id)
        return repo.assignment_dict(row)


def update_assignment(user: Optional[Mapping[str, Any]], assignment_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
    actor = require_pgy_roles(user, {"student", "education_admin"})
    with transaction() as (conn, kind):
        row = repo.get_assignment(conn, kind, assignment_id)
        if not row:
            raise ApiError("ASSIGNMENT_NOT_FOUND", "找不到指派。", status=404)
        role = _role(actor)
        if role == "student":
            if row.get("learner_username") != _username(actor.get("username")):
                raise ApiError("FORBIDDEN", "只能更新自己的指派。", status=403)
            if row.get("status") != "assigned":
                raise ApiError("CONFLICT", "送出後即鎖定學員內容；如需修改請由教學管理者退回。", status=409)
            evidence = data.get("evidence", repo.json_load(row.get("evidence"), {}))
            if not isinstance(evidence, (dict, list)):
                raise ApiError("INVALID_EVIDENCE", "evidence 必須是 JSON 物件或陣列。", status=400)
            evidence_text = repo.json_dump(evidence)
            if len(evidence_text) > 30000:
                raise ApiError("EVIDENCE_TOO_LONG", "佐證內容過長，請改放教材/檔案連結。", status=400)
            reflection = _text(data.get("reflection", row.get("reflection", "")), 12000)
            now = utcnow()
            repo.update_assignment_draft(
                conn,
                kind,
                assignment_id,
                {"evidence": evidence_text, "reflection": reflection, "updated_at": now},
            )
            repo.write_audit(
                conn,
                kind,
                assignment_id=assignment_id,
                action="student_edit",
                from_status=str(row.get("status", "")),
                to_status=str(row.get("status", "")),
                actor_username=_username(actor.get("username")),
                actor_role=role,
                detail={"evidenceUpdated": "evidence" in data, "reflectionUpdated": "reflection" in data},
            )
        else:
            if row.get("status") != "assigned":
                raise ApiError("CONFLICT", "只有尚未送出的指派可以調整教師、課程或期限。", status=409)
            fields: dict[str, Any] = {}
            detail: dict[str, Any] = {}
            if "teacherUsername" in data:
                teacher_username = _username(data.get("teacherUsername"))
                teacher = repo.find_user(conn, kind, teacher_username)
                if not teacher or not bool(teacher.get("active", True)) or normalize_role(teacher.get("role")) != "clinical_teacher":
                    raise ApiError("INVALID_TEACHER", "新指派教師不存在、已停用或角色不是臨床教師。", status=400)
                fields["teacher_username"] = teacher_username
                detail["teacherUsername"] = teacher_username
            for key, column, limit in (("title", "title", 180), ("instructions", "instructions", 10000), ("dueAt", "due_at", 80)):
                if key in data:
                    value = _text(data.get(key), limit)
                    fields[column] = value
                    detail[key] = value
            if not fields:
                raise ApiError("NO_FIELDS", "沒有可更新的欄位。", status=400)
            fields["updated_at"] = utcnow()
            repo.update_assignment_draft(conn, kind, assignment_id, fields)
            repo.write_audit(
                conn,
                kind,
                assignment_id=assignment_id,
                action="admin_edit",
                from_status=str(row.get("status", "")),
                to_status=str(row.get("status", "")),
                actor_username=_username(actor.get("username")),
                actor_role=role,
                detail=detail,
            )
        updated = repo.get_assignment(conn, kind, assignment_id)
        return repo.assignment_dict(updated)


def _apply_transition(
    conn,
    kind: str,
    actor: Mapping[str, Any],
    assignment_id: str,
    action: str,
    data: Mapping[str, Any],
) -> dict[str, Any]:
    row = repo.get_assignment(conn, kind, assignment_id)
    if not row:
        raise ApiError("ASSIGNMENT_NOT_FOUND", "找不到指派。", status=404)
    role = _role(actor)
    username = _username(actor.get("username"))
    if not transition_allowed(str(row.get("status")), action, role):
        raise ApiError("CONFLICT", f"目前狀態 {row.get('status')} 無法執行 {action}。", status=409)
    source = expected_status_for(action)
    target = target_status_for(action)
    extra: dict[str, Any] = {"updated_at": utcnow()}
    if action == "submit":
        if row.get("learner_username") != username:
            raise ApiError("FORBIDDEN", "只能送出自己的指派。", status=403)
        evidence = repo.json_load(row.get("evidence"), {})
        reflection = str(row.get("reflection", "")).strip()
        if not evidence and not reflection:
            raise ApiError("INCOMPLETE_SUBMISSION", "送出前至少需填寫反思或佐證內容。", status=400)
        extra["student_submitted_at"] = extra["updated_at"]
        detail = {"submittedAt": extra["student_submitted_at"]}
    elif action == "teacher_sign":
        if row.get("teacher_username") != username:
            raise ApiError("FORBIDDEN", "只有此指派指定的臨床教師可以簽核。", status=403)
        signature = {
            "username": username,
            "name": actor.get("name", ""),
            "signedAt": extra["updated_at"],
            "comment": _text(data.get("comment"), 4000),
        }
        extra["teacher_signature"] = repo.json_dump(signature)
        detail = {"comment": signature["comment"]}
    elif action == "group_countersign":
        if row.get("group_key") != _user_group(actor):
            raise ApiError("FORBIDDEN", "組長只能複核自己組別的指派。", status=403)
        signature = {
            "username": username,
            "name": actor.get("name", ""),
            "signedAt": extra["updated_at"],
            "comment": _text(data.get("comment"), 4000),
        }
        extra["group_signature"] = repo.json_dump(signature)
        detail = {"comment": signature["comment"]}
    else:
        confirmation = {
            "username": username,
            "name": actor.get("name", ""),
            "confirmedAt": extra["updated_at"],
            "comment": _text(data.get("comment"), 4000),
        }
        extra["final_confirmation"] = repo.json_dump(confirmation)
        detail = {"comment": confirmation["comment"]}
    try:
        repo.transition_status(conn, kind, assignment_id, source, target, extra)
    except repo.TransitionConflict as exc:
        raise ApiError("TRANSITION_CONFLICT", str(exc), status=409) from exc
    repo.write_audit(
        conn,
        kind,
        assignment_id=assignment_id,
        action=action,
        from_status=source,
        to_status=target,
        actor_username=username,
        actor_role=role,
        detail=detail,
    )
    updated = repo.get_assignment(conn, kind, assignment_id)
    return repo.assignment_dict(updated)


def submit_assignment(user: Optional[Mapping[str, Any]], assignment_id: str, data: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    actor = require_pgy_roles(user, {"student"})
    with transaction() as (conn, kind):
        return _apply_transition(conn, kind, actor, assignment_id, "submit", data or {})


def teacher_sign_assignment(user: Optional[Mapping[str, Any]], assignment_id: str, data: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    actor = require_pgy_roles(user, {"clinical_teacher"})
    with transaction() as (conn, kind):
        return _apply_transition(conn, kind, actor, assignment_id, "teacher_sign", data or {})


def group_countersign_assignment(user: Optional[Mapping[str, Any]], assignment_id: str, data: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    actor = require_pgy_roles(user, {"group_leader"})
    with transaction() as (conn, kind):
        return _apply_transition(conn, kind, actor, assignment_id, "group_countersign", data or {})


def finalize_assignment(user: Optional[Mapping[str, Any]], assignment_id: str, data: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    actor = require_pgy_roles(user, {"education_admin"})
    with transaction() as (conn, kind):
        return _apply_transition(conn, kind, actor, assignment_id, "finalize", data or {})


def reopen_assignment(user: Optional[Mapping[str, Any]], assignment_id: str, data: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    actor = require_pgy_roles(user, {"education_admin"})
    payload = data or {}
    reason = _text(payload.get("reason"), 4000)
    if not reason:
        raise ApiError("REASON_REQUIRED", "退回/重開必須填寫原因。", status=400)
    with transaction() as (conn, kind):
        row = repo.get_assignment(conn, kind, assignment_id)
        if not row:
            raise ApiError("ASSIGNMENT_NOT_FOUND", "找不到指派。", status=404)
        old = str(row.get("status", ""))
        if not can_reopen(old):
            raise ApiError("CONFLICT", "目前狀態不需要退回。", status=409)
        now = utcnow()
        try:
            repo.transition_status(
                conn,
                kind,
                assignment_id,
                old,
                "assigned",
                {
                    "student_submitted_at": "",
                    "teacher_signature": "{}",
                    "group_signature": "{}",
                    "final_confirmation": "{}",
                    "updated_at": now,
                },
            )
        except repo.TransitionConflict as exc:
            raise ApiError("TRANSITION_CONFLICT", str(exc), status=409) from exc
        repo.write_audit(
            conn,
            kind,
            assignment_id=assignment_id,
            action="reopen",
            from_status=old,
            to_status="assigned",
            actor_username=_username(actor.get("username")),
            actor_role=_role(actor),
            detail={"reason": reason},
        )
        updated = repo.get_assignment(conn, kind, assignment_id)
        return repo.assignment_dict(updated)


def cancel_assignment(user: Optional[Mapping[str, Any]], assignment_id: str, data: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    actor = require_pgy_roles(user, {"education_admin"})
    payload = data or {}
    reason = _text(payload.get("reason"), 4000)
    if not reason:
        raise ApiError("REASON_REQUIRED", "取消指派必須填寫原因。", status=400)
    with transaction() as (conn, kind):
        row = repo.get_assignment(conn, kind, assignment_id)
        if not row:
            raise ApiError("ASSIGNMENT_NOT_FOUND", "找不到指派。", status=404)
        old = str(row.get("status", ""))
        if not can_cancel(old):
            raise ApiError("CONFLICT", "已取消或已完成的指派不可直接取消。", status=409)
        now = utcnow()
        try:
            repo.transition_status(conn, kind, assignment_id, old, "cancelled", {"updated_at": now})
        except repo.TransitionConflict as exc:
            raise ApiError("TRANSITION_CONFLICT", str(exc), status=409) from exc
        repo.write_audit(
            conn,
            kind,
            assignment_id=assignment_id,
            action="cancel",
            from_status=old,
            to_status="cancelled",
            actor_username=_username(actor.get("username")),
            actor_role=_role(actor),
            detail={"reason": reason},
        )
        updated = repo.get_assignment(conn, kind, assignment_id)
        return repo.assignment_dict(updated)


def list_audit(user: Optional[Mapping[str, Any]], assignment_id: str = "") -> list[dict[str, Any]]:
    actor = require_pgy_roles(user, AUDIT_VIEW_ROLES)
    conn, kind = get_connection()
    try:
        group_key = _user_group(actor) if _role(actor) == "group_leader" else ""
        rows = repo.list_audit(conn, kind, assignment_id=_text(assignment_id, 80), group_key=group_key)
        return [repo.audit_dict(row) for row in rows]
    finally:
        conn.close()
