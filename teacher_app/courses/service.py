"""Canonical course and teaching-plan behavior.

Course validation and persistence orchestration use canonical repositories;
the public URL and response contracts remain unchanged for compatibility.
"""
from __future__ import annotations

import datetime
import json
import re
import uuid
from typing import Any, Mapping

from teacher_app.common import db as common_db
from teacher_app.common import scope
from teacher_app.common.errors import ApiError
from teacher_app.assessments import repository as assessments_repository
from teacher_app.courses import repository
from teacher_app.materials import repository as materials_repository


def _fail(code: str, message: str, status: int = 400) -> ApiError:
    return ApiError(code, message, status=status)


def list_courses(base, area: str | None, group: str | None, include_inactive: bool) -> list[dict]:
    normalized_area = scope.normalize_area(area) if area else None
    normalized_group = scope.normalize_group(group) if group else None
    return repository.list_courses(normalized_area, normalized_group, include_inactive)


def create_course(base, data: Mapping[str, Any]) -> dict:
    area = scope.normalize_area(str(data.get("area", "pgy")))
    group = scope.normalize_group(str(data.get("group", scope.DEFAULT_GROUP)))
    title = str(data.get("title", "")).strip()[:255]
    desc = str(data.get("desc", "")).strip()[:2000]
    if not title:
        raise _fail("COURSE_TITLE_REQUIRED", "請輸入課程名稱")

    course_id = f"course-{uuid.uuid4().hex[:12]}"
    return repository.create_course(
        course_id=course_id,
        area=area,
        group=group,
        title=title,
        description=desc,
        date_added=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def update_course(base, course_id: str, data: Mapping[str, Any]) -> dict:
    entry = repository.get_course(course_id)
    if not entry:
        raise _fail("COURSE_NOT_FOUND", "找不到課程", 404)
    title = str(data.get("title", entry["title"])).strip()[:255]
    desc = str(data.get("desc", entry.get("desc", ""))).strip()[:2000]
    active = bool(data.get("active", entry.get("active", True)))
    repository.update_course(course_id, title=title, description=desc, active=active)
    return {"ok": True}


def delete_course(base, course_id: str) -> dict:
    if not repository.get_course(course_id):
        raise _fail("COURSE_NOT_FOUND", "找不到課程", 404)
    with common_db.transaction() as (conn, kind):
        materials_repository.clear_course_assignment(conn, kind, course_id)
        assessments_repository.clear_course_links_on_connection(conn, kind, course_id)
        repository.delete_course_on_connection(conn, kind, course_id)
    return {"ok": True}


def get_teaching_plan(base, course_id: str) -> dict:
    course = repository.get_course(course_id)
    if not course:
        raise _fail("COURSE_NOT_FOUND", "找不到課程", 404)
    materials = [
        material
        for material in materials_repository.list_uploaded_materials(base, True)
        if material.get("courseId") == course_id
    ]
    return {"course": course, "materials": materials}


def save_teaching_plan(base, course_id: str, data: Any) -> dict:
    course = repository.get_course(course_id)
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
        valid = materials_repository.material_ids_for_course(conn, kind, course_id)
        if set(material_order) != valid:
            raise _fail(
                "COURSE_MATERIALS_CHANGED",
                "教材清單已變更，請關閉後重新開啟課程編排再儲存",
                409,
            )
        repository.update_plan_on_connection(
            conn,
            kind,
            course_id,
            {
                "title": title.strip(),
                "description": desc.strip(),
                "learning_objectives": objectives.strip(),
                "estimated_minutes": minutes,
                "start_date": start,
                "end_date": end,
                "material_order": json.dumps(material_order),
                "sort_order": order,
                "active": active if kind == "postgres" else int(active),
            },
        )
    return repository.get_course(course_id)
