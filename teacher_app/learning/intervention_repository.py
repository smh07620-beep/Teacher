"""Persistence for F3 training intervention cases."""
from __future__ import annotations

import json
from typing import Any, Mapping

from teacher_app.common import db as common_db


ACTIVE_STATUSES = {"open", "in_progress", "ready_for_retest"}
TERMINAL_STATUSES = {"resolved", "cancelled"}


def _json(value: Any) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _project(row) -> dict | None:
    if not row:
        return None
    data = dict(row)
    return {
        "id": str(data.get("id") or ""),
        "username": str(data.get("username") or "").lower(),
        "empId": str(data.get("emp_id") or ""),
        "courseId": str(data.get("course_id") or ""),
        "sourceStatus": str(data.get("source_status") or ""),
        "kind": str(data.get("kind") or ""),
        "status": str(data.get("status") or "open"),
        "learnerMessage": str(data.get("learner_message") or ""),
        "internalNote": str(data.get("internal_note") or ""),
        "plan": _json(data.get("plan_json")),
        "createdBy": str(data.get("created_by") or ""),
        "createdAt": str(data.get("created_at") or ""),
        "updatedBy": str(data.get("updated_by") or ""),
        "updatedAt": str(data.get("updated_at") or ""),
        "resolvedAt": str(data.get("resolved_at") or ""),
        "resolution": _json(data.get("resolution_json")),
    }


def get_intervention(intervention_id: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM training_interventions WHERE id={ph}",
            (str(intervention_id or ""),),
        ).fetchone()
    return _project(row)


def find_active(username: str, course_id: str) -> dict | None:
    statuses = tuple(sorted(ACTIVE_STATUSES))
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        marks = ",".join(ph for _ in statuses)
        row = conn.execute(
            f"SELECT * FROM training_interventions "
            f"WHERE LOWER(username)={ph} AND course_id={ph} AND status IN ({marks}) "
            "ORDER BY updated_at DESC LIMIT 1",
            (str(username or "").lower(), str(course_id or ""), *statuses),
        ).fetchone()
    return _project(row)


def list_interventions(
    *,
    username: str = "",
    course_id: str = "",
    status: str = "",
    include_terminal: bool = True,
    limit: int = 500,
) -> list[dict]:
    clauses = []
    params: list[Any] = []
    limit = max(1, min(1000, int(limit or 500)))
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        if username:
            clauses.append(f"LOWER(username)={ph}")
            params.append(str(username).lower())
        if course_id:
            clauses.append(f"course_id={ph}")
            params.append(str(course_id))
        if status:
            clauses.append(f"status={ph}")
            params.append(str(status))
        elif not include_terminal:
            statuses = tuple(sorted(ACTIVE_STATUSES))
            clauses.append("status IN (" + ",".join(ph for _ in statuses) + ")")
            params.extend(statuses)
        sql = "SELECT * FROM training_interventions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += f" ORDER BY updated_at DESC LIMIT {limit}"
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_project(row) for row in rows if row]


def insert_intervention(values: Mapping[str, Any]) -> dict | None:
    row = dict(values)
    columns = [
        "id", "username", "emp_id", "course_id", "source_status", "kind",
        "status", "learner_message", "internal_note", "plan_json",
        "created_by", "created_at", "updated_by", "updated_at",
        "resolved_at", "resolution_json",
    ]
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"INSERT INTO training_interventions ({','.join(columns)}) "
            f"VALUES ({','.join([ph] * len(columns))})",
            tuple(row.get(column, "") for column in columns),
        )
    return get_intervention(str(row.get("id") or ""))


def update_intervention(
    intervention_id: str,
    *,
    source_status: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    learner_message: str | None = None,
    internal_note: str | None = None,
    plan_json: str | None = None,
    updated_by: str,
    updated_at: str,
    resolved_at: str | None = None,
    resolution_json: str | None = None,
) -> dict | None:
    values = {
        "source_status": source_status,
        "kind": kind,
        "status": status,
        "learner_message": learner_message,
        "internal_note": internal_note,
        "plan_json": plan_json,
        "updated_by": updated_by,
        "updated_at": updated_at,
        "resolved_at": resolved_at,
        "resolution_json": resolution_json,
    }
    assignments = []
    params = []
    with common_db.transaction() as (conn, kind_db):
        ph = common_db.placeholder(kind_db)
        for column, value in values.items():
            if value is None:
                continue
            assignments.append(f"{column}={ph}")
            params.append(value)
        if not assignments:
            return get_intervention(intervention_id)
        params.append(str(intervention_id or ""))
        conn.execute(
            f"UPDATE training_interventions SET {','.join(assignments)} WHERE id={ph}",
            tuple(params),
        )
    return get_intervention(intervention_id)


__all__ = [
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "find_active",
    "get_intervention",
    "insert_intervention",
    "list_interventions",
    "update_intervention",
]
