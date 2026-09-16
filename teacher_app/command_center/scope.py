"""Role-scoped learner visibility for Teacher 7.1 read-only analytics."""
from __future__ import annotations

from typing import Any, Mapping, Optional

from teacher_app.common.auth import user_roles
from teacher_app.common.db import get_connection, placeholder
from teacher_app.common.errors import ApiError
from teacher_app.pgy.workflow import normalize_group


def _username(value: Any) -> str:
    return str(value or "").strip().lower()[:100]


def _active(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def resolve_scope(user: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if not user:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入後再查看訓練分析。",
            status=401,
            extra={"loginRequired": True},
        )

    roles = set(user_roles(user))
    group = normalize_group(user.get("preferredGroup") or user.get("preferred_group"))
    username = _username(user.get("username"))

    if "education_admin" in roles:
        return {"kind": "all", "roles": sorted(roles), "group": ""}
    if "group_leader" in roles:
        return {"kind": "group", "roles": sorted(roles), "group": group}
    if "clinical_teacher" in roles:
        return {"kind": "assigned", "roles": sorted(roles), "group": group, "username": username}
    if "student" in roles:
        return {"kind": "self", "roles": sorted(roles), "group": group, "username": username}

    raise ApiError(
        "FORBIDDEN",
        "此角色目前沒有訓練分析檢視範圍。",
        status=403,
    )


def _learner_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "username": _username(row.get("username")),
        "name": str(row.get("display_name") or row.get("name") or "").strip()[:100],
        "empId": str(row.get("emp_id") or row.get("empId") or "").strip()[:100],
        "group": normalize_group(row.get("preferred_group") or row.get("preferredGroup")),
    }


def visible_learners(user: Optional[Mapping[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scope = resolve_scope(user)
    if scope["kind"] == "self":
        learner = {
            "username": _username(user.get("username")),
            "name": str(user.get("name") or "").strip()[:100],
            "empId": str(user.get("empId") or user.get("emp_id") or "").strip()[:100],
            "group": normalize_group(user.get("preferredGroup") or user.get("preferred_group")),
        }
        return scope, [learner] if learner["username"] else []

    conn, kind = get_connection()
    ph = placeholder(kind)
    try:
        if scope["kind"] == "assigned":
            rows = conn.execute(
                f"""
                SELECT u.username,u.display_name,u.emp_id,u.role,u.roles_json,
                       u.preferred_group,u.active
                FROM user_accounts u
                WHERE u.username IN (
                    SELECT DISTINCT learner_username
                    FROM pgy_assignments
                    WHERE teacher_username={ph}
                      AND training_area='pgy'
                      AND status<>'cancelled'
                )
                """,
                (scope["username"],),
            ).fetchall()
        elif scope["kind"] == "group":
            rows = conn.execute(
                f"""
                SELECT username,display_name,emp_id,role,roles_json,preferred_group,active
                FROM user_accounts
                WHERE preferred_group={ph}
                """,
                (scope["group"],),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT username,display_name,emp_id,role,roles_json,preferred_group,active
                FROM user_accounts
                """
            ).fetchall()
    finally:
        conn.close()

    learners = []
    for raw in rows:
        row = dict(raw)
        if not _active(row.get("active")):
            continue
        if "student" not in set(user_roles(row)):
            continue
        learner = _learner_dict(row)
        if learner["username"] and learner["empId"]:
            learners.append(learner)

    learners.sort(key=lambda item: (item["group"], item["name"], item["empId"]))
    return scope, learners
