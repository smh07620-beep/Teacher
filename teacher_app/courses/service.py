"""Canonical course and teaching-plan behavior.

Storage remains on the legacy application object during Stage 5.1; this module
owns course validation, persistence orchestration and response data while the
public URL contract stays unchanged.
"""
from __future__ import annotations

import datetime
import json
import re
import uuid
from typing import Any, Mapping

from teacher_app.common import db as common_db
from teacher_app.common.errors import ApiError
from teacher_app.materials import repository as materials_repository


def _fail(code: str, message: str, status: int = 400) -> ApiError:
    return ApiError(code, message, status=status)


def list_courses(base, area: str | None, group: str | None, include_inactive: bool) -> list[dict]:
    normalized_area = base.normalize_area(area) if area else None
    normalized_group = base.normalize_group(group) if group else None
    return base.list_courses(normalized_area, normalized_group, include_inactive)


def create_course(base, data: Mapping[str, Any]) -> dict:
    area = base.normalize_area(str(data.get("area", "pgy")))
    group = base.normalize_group(str(data.get("group", base.DEFAULT_GROUP)))
    title = str(data.get("title", "")).strip()[:255]
    desc = str(data.get("desc", "")).strip()[:2000]
    if not title:
        raise _fail("COURSE_TITLE_REQUIRED", "請輸入課程名稱")

    course_id = f"course-{uuid.uuid4().hex[:12]}"
    conn, kind = base._db_conn()
    ph = "%s" if kind == "postgres" else "?"
    try:
        row = conn.execute(
            f"SELECT COALESCE(MAX(sort_order),-1) AS m FROM courses WHERE training_area={ph} AND group_key={ph}",
            (area, group),
        ).fetchone()
        order = (row["m"] if isinstance(row, dict) else row[0]) + 1
        date_added = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        if kind == "postgres":
            conn.execute(
                "INSERT INTO courses (id,training_area,group_key,title,description,sort_order,date_added,active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (course_id, area, group, title, desc, order, date_added, True),
            )
        else:
            conn.execute(
                "INSERT INTO courses (id,training_area,group_key,title,description,sort_order,date_added,active) VALUES (?,?,?,?,?,?,?,?)",
                (course_id, area, group, title, desc, order, date_added, 1),
            )
    finally:
        conn.close()
    return base.get_course(course_id)


def update_course(base, course_id: str, data: Mapping[str, Any]) -> dict:
    entry = base.get_course(course_id)
    if not entry:
        raise _fail("COURSE_NOT_FOUND", "找不到課程", 404)
    title = str(data.get("title", entry["title"])).strip()[:255]
    desc = str(data.get("desc", entry.get("desc", ""))).strip()[:2000]
    active = bool(data.get("active", entry.get("active", True)))
    conn, kind = base._db_conn()
    try:
        if kind == "postgres":
            conn.execute(
                "UPDATE courses SET title=%s,description=%s,active=%s WHERE id=%s",
                (title, desc, active, course_id),
            )
        else:
            conn.execute(
                "UPDATE courses SET title=?,description=?,active=? WHERE id=?",
                (title, desc, int(active), course_id),
            )
    finally:
        conn.close()
    return {"ok": True}


def delete_course(base, course_id: str) -> dict:
    if not base.get_course(course_id):
        raise _fail("COURSE_NOT_FOUND", "找不到課程", 404)
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        materials_repository.clear_course_assignment(conn, kind, course_id)
        conn.execute(f"UPDATE quiz_categories SET course_id='' WHERE course_id={ph}", (course_id,))
        conn.execute(f"DELETE FROM courses WHERE id={ph}", (course_id,))
    return {"ok": True}


def get_teaching_plan(base, course_id: str) -> dict:
    course = base.get_course(course_id)
    if not course:
        raise _fail("COURSE_NOT_FOUND", "找不到課程", 404)
    materials = [
        material
        for material in materials_repository.list_uploaded_materials(base, True)
        if material.get("courseId") == course_id
    ]
    return {"course": course, "materials": materials}


def save_teaching_plan(base, course_id: str, data: Any) -> dict:
    course = base.get_course(course_id)
    if not course:
        raise _fail("COURSE_NOT_FOUND", "找不到課程", 404)
    if not isinstance(data, dict):
        raise _fail("COURSE_PAYLOAD_INVALID", "課程資料格式不正確")

    try:
        title = data.get("title", course["title"])
        desc = data.get("desc", course["desc"])
        objectives = data.get("learningObjectives", course["learningObjectives"])
        if not isinstance(title, str) or not title.strip() or len(title) > 255:
            raise ValueError("請輸入 1–255 字的課程名稱")
        if (
            not isinstance(desc, str)
            or len(desc) > 2000
            or not isinstance(objectives, str)
            or len(objectives) > 4000
        ):
            raise ValueError("課程說明限 2000 字，學習目標限 4000 字")
        minutes = data.get("estimatedMinutes", course["estimatedMinutes"])
        order = data.get("sortOrder", course["sortOrder"])
        if type(minutes) is not int or not 0 <= minutes <= 10000 or type(order) is not int or not 0 <= order <= 100000:
            raise ValueError("建議分鐘數與顯示順序須為有效非負整數")
        start = data.get("startDate", course["startDate"])
        end = data.get("endDate", course["endDate"])
        for date_value in (start, end):
            if not isinstance(date_value, str):
                raise ValueError("日期格式不正確")
            if date_value and (
                not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value)
                or not datetime.date.fromisoformat(date_value)
            ):
                raise ValueError("日期格式不正確")
        if start and end and start > end:
            raise ValueError("結束日期不可早於開始日期")
        active = data.get("active", course["active"])
        if type(active) is not bool:
            raise ValueError("課程狀態格式不正確")
        material_order = data.get("materialOrder", course["materialOrder"])
        if (
            not isinstance(material_order, list)
            or any(not isinstance(item, str) for item in material_order)
            or len(set(material_order)) != len(material_order)
        ):
            raise ValueError("教材順序格式不正確或含重複教材")
    except (ValueError, TypeError) as exc:
        raise _fail("COURSE_PLAN_INVALID", str(exc)) from exc

    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        valid = materials_repository.material_ids_for_course(conn, kind, course_id)
        if set(material_order) != valid:
            raise _fail(
                "COURSE_MATERIALS_CHANGED",
                "教材清單已變更，請關閉後重新開啟課程編排再儲存",
                409,
            )
        values = (
            title.strip(),
            desc.strip(),
            objectives.strip(),
            minutes,
            start,
            end,
            json.dumps(material_order),
            order,
            active if kind == "postgres" else int(active),
            course_id,
        )
        fields = [
            "title",
            "description",
            "learning_objectives",
            "estimated_minutes",
            "start_date",
            "end_date",
            "material_order",
            "sort_order",
            "active",
        ]
        conn.execute(
            f"UPDATE courses SET {','.join(f'{field}={ph}' for field in fields)} WHERE id={ph}",
            values,
        )
    return base.get_course(course_id)
