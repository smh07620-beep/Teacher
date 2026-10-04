"""Canonical course data access.

All runtime SQL for the course aggregate lives here.  Services own validation
and cross-domain orchestration; the legacy host only keeps thin compatibility
delegates while the final factory cutover is pending.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

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
    lifecycle = str(r.pop("lifecycle_status", "") or "").strip()
    r["lifecycleStatus"] = lifecycle or ("published" if r["active"] else "draft")
    r["publishedAt"] = r.pop("published_at", "")
    r["endedAt"] = r.pop("ended_at", "")
    r["archivedAt"] = r.pop("archived_at", "")
    r["lifecycleUpdatedAt"] = r.pop("lifecycle_updated_at", "")
    r["lifecycleUpdatedBy"] = r.pop("lifecycle_updated_by", "")
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


def create_course(
    *,
    course_id: str,
    area: str,
    group: str,
    title: str,
    description: str,
    date_added: str,
    active: bool = True,
    lifecycle_status: str | None = None,
    lifecycle_updated_by: str = "",
) -> dict | None:
    with common_db.transaction() as (conn, kind):
        order = next_sort_order_on_connection(conn, kind, area=area, group=group)
        insert_course_on_connection(
            conn,
            kind,
            course_id=course_id,
            area=area,
            group=group,
            title=title,
            description=description,
            sort_order=order,
            date_added=date_added,
            active=active,
            lifecycle_status=lifecycle_status or ("published" if active else "draft"),
            lifecycle_updated_by=lifecycle_updated_by,
        )
    return get_course(course_id)


def next_sort_order_on_connection(conn, kind: str, *, area: str, group: str) -> int:
    ph = common_db.placeholder(kind)
    row = conn.execute(
        f"SELECT COALESCE(MAX(sort_order),-1) AS m FROM courses WHERE training_area={ph} AND group_key={ph}",
        (area, group),
    ).fetchone()
    current = dict(row).get("m", -1) if row is not None else -1
    return int(current if current is not None else -1) + 1


def insert_course_on_connection(
    conn,
    kind: str,
    *,
    course_id: str,
    area: str,
    group: str,
    title: str,
    description: str,
    sort_order: int,
    date_added: str,
    active: bool,
    lifecycle_status: str | None = None,
    lifecycle_updated_by: str = "",
) -> None:
    ph = common_db.placeholder(kind)
    if kind == "postgres":
        columns = {
            str(dict(row).get("column_name") or "")
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name=%s",
                ("courses",),
            ).fetchall()
        }
    else:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(courses)").fetchall()}
    names = ["id","training_area","group_key","title","description","sort_order","date_added","active"]
    values = [
        course_id, area, group, title, description, sort_order, date_added,
        active if kind == "postgres" else int(active),
    ]
    if "lifecycle_status" in columns:
        names.extend(["lifecycle_status","lifecycle_updated_by"])
        values.extend([
            lifecycle_status or ("published" if active else "draft"),
            str(lifecycle_updated_by or "")[:100],
        ])
    conn.execute(
        f"INSERT INTO courses ({','.join(names)}) VALUES ({','.join([ph] * len(names))})",
        tuple(values),
    )



def update_lifecycle(
    course_id: str,
    *,
    status: str,
    active: bool,
    actor: str,
    updated_at: str,
) -> dict | None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        if kind == "postgres":
            columns = {
                str(dict(row).get("column_name") or "")
                for row in conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema=current_schema() AND table_name=%s",
                    ("courses",),
                ).fetchall()
            }
        else:
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(courses)").fetchall()}
        if "lifecycle_status" not in columns:
            conn.execute(
                f"UPDATE courses SET active={ph} WHERE id={ph}",
                (active if kind == "postgres" else int(active), course_id),
            )
        else:
            assignments = [
                f"lifecycle_status={ph}",
                f"active={ph}",
                f"lifecycle_updated_at={ph}",
                f"lifecycle_updated_by={ph}",
            ]
            params = [status, active if kind == "postgres" else int(active), updated_at, str(actor or "")[:100]]
            timestamp_column = {"published": "published_at", "ended": "ended_at", "archived": "archived_at"}.get(status)
            if timestamp_column:
                assignments.append(f"{timestamp_column}={ph}")
                params.append(updated_at)
            params.append(course_id)
            conn.execute(
                f"UPDATE courses SET {','.join(assignments)} WHERE id={ph}",
                tuple(params),
            )
    return get_course(course_id)

def update_course(course_id: str, *, title: str, description: str, active: bool) -> None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"UPDATE courses SET title={ph},description={ph},active={ph} WHERE id={ph}",
            (title, description, active if kind == "postgres" else int(active), course_id),
        )


def delete_course_on_connection(conn, kind: str, course_id: str) -> None:
    ph = common_db.placeholder(kind)
    conn.execute(f"DELETE FROM courses WHERE id={ph}", (course_id,))


def update_plan_on_connection(
    conn,
    kind: str,
    course_id: str,
    values: Mapping[str, Any],
) -> None:
    ph = common_db.placeholder(kind)
    fields = (
        "title",
        "description",
        "learning_objectives",
        "estimated_minutes",
        "start_date",
        "end_date",
        "material_order",
        "sort_order",
        "active",
    )
    params = tuple(values[field] for field in fields) + (course_id,)
    conn.execute(
        f"UPDATE courses SET {','.join(f'{field}={ph}' for field in fields)} WHERE id={ph}",
        params,
    )
