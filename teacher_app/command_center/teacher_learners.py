"""Read-only teacher trainee projection for the assessment workspace.

The PGY assignment workflow remains the source of teacher/learner ownership.
This projection never grants signing authority and never trusts browser-supplied
teacher, group, or learner scope.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Optional

from teacher_app.common import db as common_db
from teacher_app.common.auth import has_permission
from teacher_app.common.errors import ApiError
from teacher_app.pgy.workflow import normalize_group


_STATUS_LABELS = {
    "assigned": "學習中",
    "submitted": "待教師簽核",
    "teacher_signed": "待複核",
    "leader_reviewed": "待行政確認",
    "finalized": "已完成",
    "cancelled": "已取消",
}


def _username(value: Any) -> str:
    return str(value or "").strip().lower()[:100]


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


def _scope(user: Mapping[str, Any]) -> dict[str, str]:
    if has_permission(user, "student.view_all"):
        return {"kind": "organization", "group": ""}
    group = normalize_group(
        user.get("preferredGroup") or user.get("preferred_group") or ""
    )
    if has_permission(user, "student.view_group"):
        return {"kind": "group", "group": group}
    if has_permission(user, "student.view_assigned"):
        return {"kind": "assigned", "group": group}
    raise ApiError("FORBIDDEN", "此帳號沒有檢視學員的權限。", status=403)


def build_teacher_learners(
    user: Optional[Mapping[str, Any]],
    *,
    now: Optional[dt.datetime] = None,
) -> dict[str, Any]:
    if not user:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入後再查看學員。",
            status=401,
            extra={"loginRequired": True},
        )

    scope = _scope(user)
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)
    username = _username(user.get("username"))

    try:
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            where = ["a.training_area='pgy'", "a.status<>'cancelled'"]
            params: list[Any] = []
            if scope["kind"] == "assigned":
                where.append(f"a.teacher_username={ph}")
                params.append(username)
            elif scope["kind"] == "group":
                where.append(f"a.group_key={ph}")
                params.append(scope["group"])
            rows = conn.execute(
                """
                SELECT a.learner_username,
                       COALESCE(u.display_name,'') AS learner_name,
                       COALESCE(u.emp_id,'') AS learner_emp_id,
                       u.active AS learner_active,
                       a.group_key,a.status,a.due_at,a.updated_at
                FROM pgy_assignments a
                LEFT JOIN user_accounts u ON u.username=a.learner_username
                WHERE """
                + " AND ".join(where)
                + " ORDER BY a.updated_at DESC",
                tuple(params),
            ).fetchall()
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(
            "TEACHER_LEARNERS_UNAVAILABLE",
            "目前無法讀取負責學員，請稍後再試。",
            status=503,
        ) from exc

    learners: dict[str, dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        learner_username = _username(row.get("learner_username"))
        if not learner_username:
            continue
        item = learners.setdefault(
            learner_username,
            {
                "username": learner_username,
                "name": str(row.get("learner_name") or learner_username)[:100],
                "empId": str(row.get("learner_emp_id") or "")[:100],
                "group": normalize_group(row.get("group_key")),
                "active": True if row.get("learner_active") is None else bool(row.get("learner_active")),
                "assignmentCount": 0,
                "completedAssignments": 0,
                "awaitingTeacher": 0,
                "awaitingLeader": 0,
                "awaitingFinalize": 0,
                "overdueAssignments": 0,
                "latestStatus": "",
                "latestStatusLabel": "",
                "lastActivityAt": "",
            },
        )
        status = str(row.get("status") or "assigned")
        item["assignmentCount"] += 1
        if status == "finalized":
            item["completedAssignments"] += 1
        elif status == "submitted":
            item["awaitingTeacher"] += 1
        elif status == "teacher_signed":
            item["awaitingLeader"] += 1
        elif status == "leader_reviewed":
            item["awaitingFinalize"] += 1

        due = _parse_datetime(row.get("due_at"))
        if due and due < current and status != "finalized":
            item["overdueAssignments"] += 1

        updated = str(row.get("updated_at") or "")
        if not item["lastActivityAt"] or updated > item["lastActivityAt"]:
            item["lastActivityAt"] = updated
            item["latestStatus"] = status
            item["latestStatusLabel"] = _STATUS_LABELS.get(status, "進行中")

    output = sorted(
        learners.values(),
        key=lambda row: (
            -int(row["overdueAssignments"] > 0),
            -int(row["awaitingTeacher"] > 0),
            str(row["name"]).lower(),
            row["username"],
        ),
    )
    return {
        "scope": scope,
        "learners": output,
        "summary": {
            "learners": len(output),
            "assignments": sum(int(row["assignmentCount"]) for row in output),
            "completedAssignments": sum(
                int(row["completedAssignments"]) for row in output
            ),
            "awaitingTeacher": sum(int(row["awaitingTeacher"]) for row in output),
            "awaitingLeader": sum(int(row["awaitingLeader"]) for row in output),
            "awaitingFinalize": sum(int(row["awaitingFinalize"]) for row in output),
            "overdueAssignments": sum(
                int(row["overdueAssignments"]) for row in output
            ),
        },
        "source": "pgy-assignments",
        "interpretation": "read_only_teacher_trainee_projection",
    }


__all__ = ["build_teacher_learners"]
