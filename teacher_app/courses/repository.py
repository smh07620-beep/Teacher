"""Canonical course data access."""
from __future__ import annotations

import json

from teacher_app.common import db as common_db
from teacher_app.common import scope


def course_row_to_dict(row) -> dict:
    r = dict(row)
    r["area"] = scope.normalize_area(r.pop("training_area", scope.DEFAULT_TRAINING_AREA))
    r["group"] = scope.normalize_group(r.pop("group_key", scope.DEFAULT_GROUP))
    r["desc"] = r.pop("description", "")
    r["sortOrder"] = int(r.pop("sort_order", 0) or 0)
    r["dateAdded"] = r.pop("date_added", "")
    r["active"] = bool(r.get("active", True))
    r["learningObjectives"] = r.pop("learning_objectives", "")
    r["estimatedMinutes"] = int(r.pop("estimated_minutes", 0) or 0)
    r["startDate"] = r.pop("start_date", "")
    r["endDate"] = r.pop("end_date", "")
    try:
        r["materialOrder"] = json.loads(r.pop("material_order", "[]") or "[]")
    except (ValueError, TypeError):
        r["materialOrder"] = []
    return r


def get_course(course_id: str) -> dict | None:
    if not course_id:
        return None
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM courses WHERE id={ph}", (course_id,)).fetchone()
    return course_row_to_dict(row) if row else None


def list_courses(area: str | None = None, group: str | None = None, include_inactive: bool = False) -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        clauses: list[str] = []
        params: list[object] = []
        if area:
            clauses.append(f"training_area={ph}")
            params.append(scope.normalize_area(area))
        if group:
            clauses.append(f"group_key={ph}")
            params.append(scope.normalize_group(group))
        if not include_inactive:
            clauses.append("active=" + ("TRUE" if kind == "postgres" else "1"))
        sql = "SELECT * FROM courses"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY sort_order ASC, date_added ASC"
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [course_row_to_dict(row) for row in rows]
