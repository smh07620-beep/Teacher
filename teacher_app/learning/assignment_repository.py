"""Persistence for general course learning assignments."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from teacher_app.common import db as common_db


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _true(kind: str) -> str:
    return "TRUE" if kind == "postgres" else "1"


def assignment_to_dict(row: Mapping[str, Any] | Any) -> dict[str, Any]:
    data = dict(row)
    data["courseId"] = str(data.pop("course_id", "") or "")
    data["area"] = str(data.pop("training_area", "") or "")
    data["group"] = str(data.pop("group_key", "") or "")
    data["assigneeType"] = str(data.pop("assignee_type", "") or "")
    data["assigneeKey"] = str(data.pop("assignee_key", "") or "")
    data["required"] = _bool(data.get("required", True))
    data["dueAt"] = str(data.pop("due_at", "") or "")
    data["assignedAt"] = str(data.pop("assigned_at", "") or "")
    data["assignedBy"] = str(data.pop("assigned_by", "") or "")
    data["active"] = _bool(data.get("active", True))
    data["createdAt"] = str(data.pop("created_at", "") or "")
    data["updatedAt"] = str(data.pop("updated_at", "") or "")
    return data


def get_assignment(assignment_id: str) -> dict[str, Any] | None:
    assignment_id = str(assignment_id or "").strip()
    if not assignment_id:
        return None
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM learning_assignments WHERE id={ph}",
            (assignment_id,),
        ).fetchone()
    return assignment_to_dict(row) if row else None


def list_active_assignments() -> list[dict[str, Any]]:
    with common_db.read_connection() as (conn, kind):
        rows = conn.execute(
            f"SELECT * FROM learning_assignments WHERE active={_true(kind)} "
            "ORDER BY due_at='',due_at,assigned_at,id"
        ).fetchall()
    return [assignment_to_dict(row) for row in rows]


def list_for_user(
    *,
    username: str,
    area: str,
    group: str,
) -> list[dict[str, Any]]:
    username = str(username or "").strip().lower()
    area = str(area or "").strip()
    group = str(group or "").strip()
    if not username:
        return []
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"""
            SELECT * FROM learning_assignments
            WHERE active={_true(kind)}
              AND (
                    (assignee_type='user' AND LOWER(assignee_key)={ph})
                 OR (assignee_type='group' AND training_area={ph} AND group_key={ph})
                 OR (assignee_type='all' AND training_area={ph})
              )
            ORDER BY required DESC,due_at='',due_at,assigned_at,id
            """,
            (username, area, group, area),
        ).fetchall()
    return [assignment_to_dict(row) for row in rows]


def insert_assignment(values: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "id",
        "course_id",
        "training_area",
        "group_key",
        "assignee_type",
        "assignee_key",
        "required",
        "due_at",
        "assigned_at",
        "assigned_by",
        "active",
        "created_at",
        "updated_at",
    )
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        stored = dict(values)
        if kind != "postgres":
            stored["required"] = int(bool(stored.get("required", True)))
            stored["active"] = int(bool(stored.get("active", True)))
        conn.execute(
            f"INSERT INTO learning_assignments ({','.join(fields)}) "
            f"VALUES ({','.join(ph for _ in fields)})",
            tuple(stored.get(field) for field in fields),
        )
    return get_assignment(str(values.get("id") or "")) or {}


def set_active(assignment_id: str, active: bool, *, updated_at: str) -> dict[str, Any] | None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        stored = active if kind == "postgres" else int(active)
        conn.execute(
            f"UPDATE learning_assignments SET active={ph},updated_at={ph} WHERE id={ph}",
            (stored, updated_at, assignment_id),
        )
    return get_assignment(assignment_id)


def course_ids(assignments: Sequence[Mapping[str, Any]]) -> set[str]:
    return {
        str(item.get("courseId") or "").strip()
        for item in assignments
        if str(item.get("courseId") or "").strip()
    }


__all__ = [
    "assignment_to_dict",
    "course_ids",
    "get_assignment",
    "insert_assignment",
    "list_active_assignments",
    "list_for_user",
    "set_active",
]
