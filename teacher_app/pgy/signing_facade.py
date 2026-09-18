"""Canonical multi-role PGY signing facade.

This module owns the 6.6 additive read/scope rules and new-assignment sign-mode
configuration. The root pgy_signing_66 module is only an HTTP compatibility
adapter after convergence.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from teacher_app.common import db as common_db
from teacher_app.common.auth import has_role, normalize_role, user_roles
from teacher_app.common.errors import ApiError
from teacher_app.common.scope import normalize_group
from teacher_app.pgy import repository as repo
from teacher_app.pgy import signing
from teacher_app.pgy import signing_repository
from teacher_app.pgy.workflow import ASSIGNMENT_STATUSES, utcnow


def _username(value: Any) -> str:
    return str(value or "").strip().lower()[:100]


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _user_group(user: Mapping[str, Any]) -> str:
    return normalize_group(user.get("preferredGroup") or user.get("preferred_group"))


def require_login(user: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    if not user:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入後再執行此操作。",
            status=401,
            extra={"loginRequired": True},
        )
    return user


def assignment_dict(row) -> dict[str, Any]:
    return signing.assignment_dict(row)


def workflow_meta(user: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    actor = require_login(user)
    roles = user_roles(actor)
    actions: list[str] = []
    if "student" in roles:
        actions.append("submit")
    if "clinical_teacher" in roles or "group_leader" in roles:
        actions.extend(["sign", "countersign"])
    if "education_admin" in roles:
        actions.extend(["create", "edit_assignment", "reopen", "cancel"])
    return {
        "statuses": sorted(ASSIGNMENT_STATUSES),
        "actions": actions,
        "role": normalize_role(actor.get("role")),
        "roles": roles,
        "signatureOrder": ["student", "clinical_teacher", "group_leader", "education_admin"],
        "signingModes": ["single", "dual"],
    }


def list_candidates(user: Optional[Mapping[str, Any]], group: str = "") -> dict[str, Any]:
    actor = require_login(user)
    roles = set(user_roles(actor))
    if not roles.intersection({"education_admin", "group_leader"}):
        raise ApiError("FORBIDDEN", "權限不足。", status=403)
    requested_group = normalize_group(group or _user_group(actor))
    if "education_admin" not in roles and "group_leader" in roles and requested_group != _user_group(actor):
        raise ApiError("FORBIDDEN", "組長只能查看自己組別的指派候選人。", status=403)
    with common_db.read_connection() as (conn, kind):
        students, teachers = signing_repository.list_candidates(conn, kind, requested_group)
    return {"group": requested_group, "students": students, "teachers": teachers}


def list_assignments(
    user: Optional[Mapping[str, Any]],
    *,
    status: str = "",
    group: str = "",
) -> list[dict[str, Any]]:
    actor = require_login(user)
    roles = set(user_roles(actor))
    permitted = {"student", "clinical_teacher", "group_leader", "education_admin"}
    if not roles.intersection(permitted):
        raise ApiError("FORBIDDEN", "權限不足。", status=403)

    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        where = ["a.training_area='pgy'"]
        params: list[Any] = []
        username = _username(actor.get("username"))
        if "education_admin" not in roles:
            scopes: list[str] = []
            if "student" in roles:
                scopes.append(f"a.learner_username={ph}")
                params.append(username)
            if "clinical_teacher" in roles:
                scopes.append(f"a.teacher_username={ph}")
                params.append(username)
            if "group_leader" in roles:
                scopes.append(f"a.group_key={ph}")
                params.append(_user_group(actor))
            if not scopes:
                raise ApiError("FORBIDDEN", "權限不足。", status=403)
            where.append("(" + " OR ".join(scopes) + ")")

        safe_status = _text(status, 40)
        if safe_status:
            if safe_status not in ASSIGNMENT_STATUSES:
                raise ApiError("INVALID_STATUS", "狀態格式不正確。", status=400)
            where.append(f"a.status={ph}")
            params.append(safe_status)

        safe_group = _text(group, 40)
        if safe_group and "education_admin" in roles:
            where.append(f"a.group_key={ph}")
            params.append(normalize_group(safe_group))

        rows = repo.list_assignments(conn, kind, " AND ".join(where), params)
        return [assignment_dict(row) for row in rows]


def get_assignment(user: Optional[Mapping[str, Any]], assignment_id: str) -> dict[str, Any]:
    actor = require_login(user)
    roles = set(user_roles(actor))
    permitted = {"student", "clinical_teacher", "group_leader", "education_admin"}
    if not roles.intersection(permitted):
        raise ApiError("FORBIDDEN", "權限不足。", status=403)
    with common_db.read_connection() as (conn, kind):
        row = repo.get_assignment(conn, kind, assignment_id)
    if not row:
        raise ApiError("ASSIGNMENT_NOT_FOUND", "找不到指派。", status=404)
    data = dict(row)
    username = _username(actor.get("username"))
    allowed = (
        "education_admin" in roles
        or ("student" in roles and data.get("learner_username") == username)
        or ("clinical_teacher" in roles and data.get("teacher_username") == username)
        or ("group_leader" in roles and normalize_group(data.get("group_key")) == _user_group(actor))
    )
    if not allowed:
        raise ApiError("FORBIDDEN", "無權查看此指派。", status=403)
    return assignment_dict(row)


def create_assignment(user: Optional[Mapping[str, Any]], data: Mapping[str, Any]) -> dict[str, Any]:
    actor = require_login(user)
    if not has_role(actor, "education_admin"):
        raise ApiError("FORBIDDEN", "權限不足。", status=403)

    learner_username = _username(data.get("learnerUsername"))
    teacher_username = _username(data.get("teacherUsername"))
    if not learner_username or not teacher_username:
        raise ApiError("INVALID_ASSIGNMENT", "學員與臨床教師皆為必填。", status=400)
    area = _text(data.get("area") or "pgy", 20)
    if area != "pgy":
        raise ApiError("INVALID_AREA", "PGY 指派只能建立在 PGY 訓練區。", status=400)
    sign_mode = signing.validate_new_sign_mode(data.get("signMode", "single"))

    with common_db.transaction() as (conn, kind):
        learner = repo.find_user(conn, kind, learner_username)
        teacher = repo.find_user(conn, kind, teacher_username)
        if not learner or not bool(learner.get("active", True)) or not has_role(learner, "student"):
            raise ApiError("INVALID_LEARNER", "指定的學員不存在、已停用或角色不是學員。", status=400)
        if not teacher or not bool(teacher.get("active", True)) or not has_role(teacher, "clinical_teacher"):
            raise ApiError("INVALID_TEACHER", "指定的教師不存在、已停用或未具臨床教師身分。", status=400)

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

        import uuid
        assignment_id = uuid.uuid4().hex
        now = utcnow()
        title = _text(data.get("title") or (course or {}).get("title") or "PGY訓練指派", 180)
        repo.create_assignment(
            conn,
            kind,
            assignment_id=assignment_id,
            learner_username=learner_username,
            teacher_username=teacher_username,
            group_key=group,
            course_id=course_id,
            title=title,
            instructions=_text(data.get("instructions"), 10000),
            due_at=_text(data.get("dueAt"), 80),
            created_by=_username(actor.get("username")),
            created_at=now,
        )
        ph = common_db.placeholder(kind)
        conn.execute(
            f"UPDATE pgy_assignments SET sign_mode={ph} WHERE id={ph}",
            (sign_mode, assignment_id),
        )
        repo.write_audit(
            conn,
            kind,
            assignment_id=assignment_id,
            action="create",
            from_status="",
            to_status="assigned",
            actor_username=_username(actor.get("username")),
            actor_role=normalize_role(actor.get("role")),
            detail={
                "learnerUsername": learner_username,
                "teacherUsername": teacher_username,
                "courseId": course_id,
                "group": group,
                "signMode": sign_mode,
            },
        )
        row = repo.get_assignment(conn, kind, assignment_id)
        return assignment_dict(row)


def update_sign_mode(user: Optional[Mapping[str, Any]], assignment_id: str, value: Any) -> dict[str, Any]:
    actor = require_login(user)
    if not has_role(actor, "education_admin"):
        raise ApiError("FORBIDDEN", "權限不足。", status=403)
    sign_mode = signing.validate_new_sign_mode(value)
    with common_db.transaction() as (conn, kind):
        row = repo.get_assignment(conn, kind, assignment_id)
        if not row:
            raise ApiError("ASSIGNMENT_NOT_FOUND", "找不到指派。", status=404)
        if str(row.get("status")) != "assigned":
            raise ApiError("CONFLICT", "只有尚未送出的指派可以修改簽核模式。", status=409)
        now = utcnow()
        repo.update_assignment_draft(
            conn,
            kind,
            assignment_id,
            {"sign_mode": sign_mode, "updated_at": now},
        )
        repo.write_audit(
            conn,
            kind,
            assignment_id=assignment_id,
            action="admin_edit",
            from_status="assigned",
            to_status="assigned",
            actor_username=_username(actor.get("username")),
            actor_role=normalize_role(actor.get("role")),
            detail={"signMode": sign_mode},
        )
        updated = repo.get_assignment(conn, kind, assignment_id)
        return assignment_dict(updated)


def get_sign_mode(assignment_id: str) -> str:
    with common_db.read_connection() as (conn, kind):
        row = signing_repository.get_sign_mode_row(conn, kind, assignment_id)
    if not row:
        raise ApiError("ASSIGNMENT_NOT_FOUND", "找不到指派。", status=404)
    return signing.normalize_sign_mode(dict(row).get("sign_mode"), "legacy")
